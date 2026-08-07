"""Agent identity and persona domain models: the agent roles/names and the
reviewer persona axes (focus, commitment, intention, knowledgeability) plus the
area-chair style. The chat-model vocabulary and response schemas live in
``domain/models/chat.py``."""
from enum import StrEnum
from pydantic import BaseModel, Field, SerializeAsAny
from typing import Any

from models.domain.chat import ChatModelName, ChatModelResponseSchema, ToolCallRecord


class AgentRole(StrEnum):
    CHAT_AGENT = "chat"
    REVIEWER = "reviewer"
    META_REVIEWER = "meta_reviewer"
    AREA_CHAIR = "area_chair"
    AUTHOR_AGENT = "author_agent"


class ContextMode(StrEnum):
    """The retrieval strategy that built / serves an index."""
    FULL_CONTEXT = "full_context"
    BM25 = "bm25"
    EMBEDDING = "embedding"
    SUMMARY = "summary"
    NONE = "none"


class AgentRequestContext(BaseModel):
    context_mode: ContextMode = ContextMode.NONE
    """The context mode used to retrieve the context for this agent"""
    retrieval_context_query: str | None = None
    """The query used to retrieve the context for this agent. If it is not None, it contains the relevant query."""
    use_retrieval_tool: bool = False
    """Whether the agent may call the paper-retrieval tool during its invocation."""
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    """How many passages each retrieval tool call returns."""
    max_tool_iterations: int = Field(default=3, ge=1, le=10)
    """Cap on tool-calling round-trips before the agent must answer."""

    @staticmethod
    def default_none_context() -> "AgentRequestContext":
        return AgentRequestContext(context_mode=ContextMode.NONE, retrieval_context_query=None)
    
    @staticmethod
    def default_full_context() -> "AgentRequestContext":
        return AgentRequestContext(context_mode=ContextMode.FULL_CONTEXT, retrieval_context_query=None)


class CreateAgentRequest(BaseModel):
    """Request to create an agent with a specific role, model, temperature, and optional system prompt."""
    paper_id: str 
    
    model: ChatModelName
    temperature: float
    agent_role: AgentRole
    agent_index: int | None = None
        
    prompt_preset_id: int

    context: AgentRequestContext = AgentRequestContext.default_none_context()
    
    retrieval_context_query: str | None = None    


class AgentResponse(BaseModel):
    """An agent's structured payload plus the token usage and traces of how it
    was produced."""
    agent_role: AgentRole
    agent_index: int | None = None
    model: ChatModelName | None = None

    response_schema: SerializeAsAny[ChatModelResponseSchema]

    system_prompt: str | None = None
    prompt_preset_id: int | None = None
    input_message: str | None = None
    context_used: str | None = None
    
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    latency_seconds: float | None = None

    tool_trace: list[ToolCallRecord] | None = None
    """Executed tool round-trips, when the agent used the retrieval tool."""

    def to_json(self) -> str:
        return self.model_dump_json(ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()