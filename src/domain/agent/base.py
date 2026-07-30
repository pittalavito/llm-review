from abc import ABC

from core.error import ValidationError, UpstreamError
from domain.chat.base import Chat, ChatResponse
from domain.models.chat import AreaChairResponseSchema, AuthorResponseSchema, ChatModelResponseSchema, MetaReviewResponseSchema, ReviewerResponseSchema
from domain.models.agent import AgentResponse, AgentRole, AgentRequestContext, ContextMode, CreateAgentRequest
from domain.models.graph import CreateGraphReviewRequest


class Factory:
    """Factory for creating agents based on their role."""

    @staticmethod
    def create_agent(request: CreateAgentRequest, chat: Chat, system_prompt: str | None = None) -> "Agent":
        ag_role = request.agent_role
        ag_id = request.agent_index
        req_context = request.context
        
        if ag_role == AgentRole.REVIEWER:
            if ag_id is None:
                raise ValueError("Reviewer agent requires an index.")
            return ReviewerAgent(chat=chat, index=ag_id, system_prompt=system_prompt, context_mode=req_context)
        elif ag_role == AgentRole.META_REVIEWER:
            return MetaReviewerAgent(chat=chat, system_prompt=system_prompt, context_mode=req_context)
        elif ag_role == AgentRole.AREA_CHAIR:
            return AreaChairAgent(chat=chat, system_prompt=system_prompt, context_mode=req_context)
        elif ag_role == AgentRole.AUTHOR_AGENT:
            return AuthorAgent(chat=chat, system_prompt=system_prompt, context_mode=req_context)
        elif ag_role == AgentRole.CHAT_AGENT:
            return ChatAgent(chat=chat, system_prompt=system_prompt, context_mode=req_context)
        else:
            raise ValueError(f"Unknown agent role: {ag_role}")

    @staticmethod
    def create_agent_requests(request: CreateGraphReviewRequest) -> list[CreateAgentRequest]:
        """Create a list of CreateAgentRequest objects for all agents in the graph."""
        config = request.graph_config
        agent_requests: list[CreateAgentRequest] = []
        
        for index in range(1, config.num_reviewers + 1):
            agent_requests.append(CreateAgentRequest(
                model=config.reviewer.model,
                temperature=config.reviewer.temperature,
                agent_role=AgentRole.REVIEWER,
                agent_index=index,
                prompt_version="default",
                paper_id=request.paper_id,
                context=config.reviewer.request_context
            ))
        
        for role, agent_config in (
            (AgentRole.META_REVIEWER, config.meta_reviewer),
            (AgentRole.AREA_CHAIR, config.area_chair),
            (AgentRole.AUTHOR_AGENT, config.author),
        ):
            agent_requests.append(CreateAgentRequest(
                model=agent_config.model,
                temperature=agent_config.temperature,
                agent_role=role,
                agent_index=None,
                prompt_version="default",
                paper_id=request.paper_id,
                context=agent_config.request_context
            ))
        
        return agent_requests
     
        
class Agent(ABC):

    def __init__(
        self,
        chat: Chat,
        agent_role: AgentRole,
        agent_index: int | None = None,
        request_context: AgentRequestContext | None = None,
        system_prompt: str | None = "",
        response_schema: type[ChatModelResponseSchema] | None = None,
    ):
        self.chat: Chat = chat
        self.agent_role: AgentRole = agent_role
        self.agent_index: int | None = agent_index
        self.agent_context: AgentRequestContext | None = request_context
        self.system_prompt: str | None = system_prompt
        self.response_schema: type[ChatModelResponseSchema] | None = response_schema
        self.context: str | None = None
    
    @property
    def name(self) -> str:
        """String identity of this agent (e.g. ``reviewer_1``, ``meta_reviewer``)."""
        return f"{self.agent_role}_{self.agent_index}" if self.agent_index is not None else str(self.agent_role)
        
    def set_context(self, context: str | None) -> None:
        if self.agent_context is None or self.agent_context.context_mode == ContextMode.NONE:
            raise ValueError("Cannot set context when context_mode is NONE.")
        self.context = context
        
    def run(self, input_message: str) -> AgentResponse:
        message = self._normalize_message(input_message)
        try:
            chat_response = self._invoke_chat(message)
        except Exception as exc:
            raise UpstreamError(f"LLM call failed for agent '{self.name}': {exc}") from exc
        return self._to_response(message, chat_response)
    
    def _invoke_chat(self, message: str) -> ChatResponse:
        return self.chat.invoke(self.system_prompt, message, self.context, self.response_schema, label=self.name)

    @staticmethod
    def _normalize_message(message: str) -> str:
        normalized = message.strip()
        if not normalized:
            raise ValidationError("Message must not be empty.")
        return normalized
    
    def _to_response(self, input_message: str, chat_response: ChatResponse) -> AgentResponse:
        return AgentResponse(
            agent_role=self.agent_role,
            agent_index=self.agent_index,
            response_schema=chat_response.response_schema,
            system_prompt=self.system_prompt,
            input_message=input_message,
            context_used=self.context,
            input_tokens=chat_response.input_tokens,
            output_tokens=chat_response.output_tokens,
            total_tokens=chat_response.total_tokens,
        )


class ReviewerAgent(Agent):
    """A reviewer, identified by its 1-based index (reviewer_1, reviewer_2, ...).
    The committee size is decided per run — the index is unbounded. Produces a
    ReviewerResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        index: int = 1,
        context_mode: AgentRequestContext | None = AgentRequestContext.default_full_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat=chat, 
            agent_role=AgentRole.REVIEWER, 
            agent_index=index, 
            system_prompt=system_prompt,
            request_context=context_mode,
            response_schema=ReviewerResponseSchema
        )


class MetaReviewerAgent(Agent):
    """Synthesizes the reviews. Produces a MetaReviewResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentRequestContext | None = AgentRequestContext.default_none_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat=chat, 
            agent_role=AgentRole.META_REVIEWER, 
            agent_index=None, 
            system_prompt=system_prompt,
            request_context=context_mode,
            response_schema=MetaReviewResponseSchema
        )


class AreaChairAgent(Agent):
    """Makes the final accept/revise decision. Produces an AreaChairResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentRequestContext | None = AgentRequestContext.default_none_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat=chat, 
            agent_role=AgentRole.AREA_CHAIR, 
            agent_index=None, 
            system_prompt=system_prompt, 
            request_context=context_mode,
            response_schema=AreaChairResponseSchema
        )


class AuthorAgent(Agent):
    """Produces the author's rebuttal and revisions. Produces an AuthorResponseSchema."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentRequestContext | None = AgentRequestContext.default_none_context(),
        system_prompt: str = "",
    ):
        super().__init__(
            chat, 
            AgentRole.AUTHOR_AGENT, 
            agent_index=None,
            system_prompt=system_prompt, 
            request_context=context_mode,
            response_schema=AuthorResponseSchema
        )


class ChatAgent(Agent):
    """A bare chat agent: no structured schema, returns the raw model reply
    (wrapped in ChatFallbackRawResponseSchema). Takes only the Chat and an
    optional system prompt."""

    def __init__(
        self,
        chat: Chat,
        context_mode: AgentRequestContext | None = AgentRequestContext.default_none_context(),
        system_prompt: str = ""
    ):
        super().__init__(
            chat=chat,
            agent_role=AgentRole.CHAT_AGENT,
            agent_index=None,
            system_prompt=system_prompt,
            request_context=context_mode,
            response_schema=None
        )