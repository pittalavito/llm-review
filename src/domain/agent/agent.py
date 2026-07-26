from abc import ABC
from enum import Enum

from core.error import ValidationError, UpstreamError
from domain.chat.chat import Chat, ChatResponse
from domain.models.agent import AgentName, AgentResponse
from domain.models.chat import (
    AreaChairResponseSchema,
    AuthorResponseSchema,
    ChatModelResponseSchema,
    MetaReviewResponseSchema,
    ReviewerResponseSchema,
)


class ContextMode(str, Enum):
    """The mode of context to use for the agent."""
    FULL = "full"
    SUMMARY = "summary"
    NONE = "none"


class Adapter:
    """Agent-layer adapter: turns a chat-level ``ChatResponse`` into an
    ``AgentResponse`` (attaching the agent name, message/context and token usage)."""

    @staticmethod
    def to_agent_response(agent: AgentName, message: str, context: str | None, chat_response: ChatResponse) -> AgentResponse:
        return AgentResponse(
            agent=agent,
            response_schema=chat_response.response_schema,
            input_message=message,
            context_used=context,
            input_tokens=chat_response.input_tokens,
            output_tokens=chat_response.output_tokens,
            total_tokens=chat_response.total_tokens,
            prompt_trace=None,
            runtime_trace=None,
        )


class Agent(ABC):

    def __init__(
        self,
        chat: Chat,
        agent_name: AgentName,
        context_mode: ContextMode = ContextMode.FULL,
        tools: list | None = None,
        system_prompt: str = "",
        response_schema: type[ChatModelResponseSchema] | None = None,
    ):
        self.name = agent_name
        self.chat = chat
        self.context_mode = context_mode
        self.system_prompt = system_prompt
        self.response_schema = response_schema
        self.tool_registry = tools

    def run(self, input_message: str, paper_id: str | None = None) -> AgentResponse:
        message = self._normalize_message(input_message)
        context = self._retrieve_context(paper_id)
        try:
            chat_response = self._invoke_chat(message, context)
        except Exception as exc:
            raise UpstreamError(f"LLM call failed for agent '{self.name}': {exc}") from exc
        return Adapter.to_agent_response(self.name, message, context, chat_response)

    def _invoke_chat(self, message: str, context: str | None) -> ChatResponse:
        return self.chat.invoke(self.system_prompt, message, context, self.response_schema, label=str(self.name))

    @staticmethod
    def _normalize_message(message: str) -> str:
        normalized = message.strip()
        if not normalized:
            raise ValidationError("Message must not be empty.")
        return normalized

    def _retrieve_context(self, paper_id: str | None) -> str | None:
        """To implement: retrieve context for the given paper_id, based on the context_mode."""
        return None


class ReviewerAgent(Agent):
    """A reviewer (default reviewer_1). Produces a ReviewerResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        agent_name: AgentName = AgentName.REVIEWER_1,
        system_prompt: str = "",
    ):
        super().__init__(chat, agent_name, system_prompt=system_prompt, response_schema=ReviewerResponseSchema)


class MetaReviewerAgent(Agent):
    """Synthesizes the reviews. Produces a MetaReviewResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        system_prompt: str = "",
    ):
        super().__init__(chat, AgentName.META_REVIEWER, system_prompt=system_prompt, response_schema=MetaReviewResponseSchema)


class AreaChairAgent(Agent):
    """Makes the final accept/revise decision. Produces an AreaChairResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        system_prompt: str = "",
    ):
        super().__init__(chat, AgentName.AREA_CHAIR, system_prompt=system_prompt, response_schema=AreaChairResponseSchema)


class AuthorAgent(Agent):
    """Produces the author's rebuttal and revisions. Produces an AuthorResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        system_prompt: str = "",
    ):
        super().__init__(chat, AgentName.AUTHOR_AGENT, system_prompt=system_prompt, response_schema=AuthorResponseSchema)
