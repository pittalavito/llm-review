from abc import ABC
from enum import Enum

from huggingface_hub import Agent

from core.error import ValidationError, UpstreamError
from domain.chat.base import Chat, ChatResponse
from domain.models.agent import AgentResponse, AgentRole, AgentContext, ContextMode, CreateAgentRequest
from domain.models.chat import (
    AreaChairResponseSchema,
    AuthorResponseSchema,
    ChatModelResponseSchema,
    MetaReviewResponseSchema,
    ReviewerResponseSchema,
)


class Adapter:
    """Agent-layer adapter: turns a chat-level ``ChatResponse`` into an
    ``AgentResponse`` (attaching the agent name, message/context and token usage)."""

    @staticmethod
    def to_agent_response(agent_role: AgentRole, agent_index: int | None, message: str, context: str | None, chat_response: ChatResponse) -> AgentResponse:
        return AgentResponse(
            agent_role=agent_role,
            agent_index=agent_index,
            response_schema=chat_response.response_schema,
            input_message=message,
            context_used=context,
            input_tokens=chat_response.input_tokens,
            output_tokens=chat_response.output_tokens,
            total_tokens=chat_response.total_tokens,
            prompt_trace=None,
            runtime_trace=None,
        )


class Factory:
    """Factory for creating agents based on their role."""

    @staticmethod
    def create_agent(request: CreateAgentRequest, chat: Chat, system_prompt: str | None = None) -> "Agent":
        agent_role = request.agent_role
        agent_index = request.agent_index
        context_mode = request.context_mode
        
        if agent_role == AgentRole.REVIEWER:
            if agent_index is None:
                raise ValueError("Reviewer agent requires an index.")
            return ReviewerAgent(chat=chat, index=agent_index, system_prompt=system_prompt, context_mode=context_mode)
        elif agent_role == AgentRole.META_REVIEWER:
            return MetaReviewerAgent(chat=chat, system_prompt=system_prompt, context_mode=context_mode)
        elif agent_role == AgentRole.AREA_CHAIR:
            return AreaChairAgent(chat=chat, system_prompt=system_prompt, context_mode=context_mode)
        elif agent_role == AgentRole.AUTHOR_AGENT:
            return AuthorAgent(chat=chat, system_prompt=system_prompt, context_mode=context_mode)
        elif agent_role == AgentRole.CHAT_AGENT:
            return ChatAgent(chat=chat, system_prompt=system_prompt, context_mode=context_mode)
        else:
            raise ValueError(f"Unknown agent role: {agent_role}")


class Agent(ABC):

    def __init__(
        self,
        chat: Chat,
        agent_role: AgentRole,
        agent_index: int | None = None,
        context_mode: AgentContext | None = None,
        system_prompt: str | None = "",
        response_schema: type[ChatModelResponseSchema] | None = None,
    ):
        self.chat: Chat = chat
        self.agent_role: AgentRole = agent_role
        self.agent_index: int | None = agent_index
        self.context_mode: AgentContext | None = context_mode
        self.system_prompt: str | None = system_prompt
        self.response_schema: type[ChatModelResponseSchema] | None = response_schema
        self.context = None
        
    def set_context(self, context: str | None) -> None:
        if self.context_mode is None or self.context_mode.context_mode == ContextMode.NONE:
            raise ValueError("Cannot set context when context_mode is NONE.")
        self.context = context
        
    def run(self, input_message: str) -> AgentResponse:
        message = self._normalize_message(input_message)
        try:
            chat_response = self._invoke_chat(message)
        except Exception as exc:
            raise UpstreamError(f"LLM call failed for agent '{self.name}': {exc}") from exc
        return Adapter.to_agent_response(self.agent_role, self.agent_index, message, self.context, chat_response)

    @property
    def name(self) -> str:
        """String identity of this agent (e.g. ``reviewer_1``, ``meta_reviewer``)."""
        return f"{self.agent_role}_{self.agent_index}" if self.agent_index is not None else str(self.agent_role)

    def _invoke_chat(self, message: str) -> ChatResponse:
        return self.chat.invoke(self.system_prompt, message, self.context, self.response_schema, label=self.name)

    @staticmethod
    def _normalize_message(message: str) -> str:
        normalized = message.strip()
        if not normalized:
            raise ValidationError("Message must not be empty.")
        return normalized


class ReviewerAgent(Agent):
    """A reviewer, identified by its 1-based index (reviewer_1, reviewer_2, ...).
    The committee size is decided per run — the index is unbounded. Produces a
    ReviewerResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        index: int = 1,
        context_mode: AgentContext | None = AgentContext.default_full_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat=chat, 
            agent_role=AgentRole.REVIEWER, 
            agent_index=index, 
            system_prompt=system_prompt,
            context_mode=context_mode,
            response_schema=ReviewerResponseSchema
        )


class MetaReviewerAgent(Agent):
    """Synthesizes the reviews. Produces a MetaReviewResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentContext | None = AgentContext.default_none_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat=chat, 
            agent_role=AgentRole.META_REVIEWER, 
            agent_index=None, 
            system_prompt=system_prompt,
            context_mode=context_mode,
            response_schema=MetaReviewResponseSchema
        )


class AreaChairAgent(Agent):
    """Makes the final accept/revise decision. Produces an AreaChairResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentContext | None = AgentContext.default_none_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat=chat, 
            agent_role=AgentRole.AREA_CHAIR, 
            agent_index=None, 
            system_prompt=system_prompt, 
            context_mode=context_mode,
            response_schema=AreaChairResponseSchema
        )


class AuthorAgent(Agent):
    """Produces the author's rebuttal and revisions. Produces an AuthorResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentContext | None = AgentContext.default_none_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat, 
            AgentRole.AUTHOR_AGENT, 
            agent_index=None,
            system_prompt=system_prompt, 
            context_mode=context_mode,
            response_schema=AuthorResponseSchema
        )


class ChatAgent(Agent):
    """A bare chat agent: no structured schema, returns the raw model reply
    (wrapped in ChatFallbackRawResponseSchema). Takes only the Chat and an
    optional system prompt."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentContext | None = AgentContext.default_none_context(),
        system_prompt: str = ""
    ):
        super().__init__(
            chat=chat,
            agent_role=AgentRole.CHAT_AGENT,
            agent_index=None,
            system_prompt=system_prompt,
            context_mode=context_mode,
            response_schema=None
        )