"""Agent identity and persona domain models: the agent roles/names and the
reviewer persona axes (focus, commitment, intention, knowledgeability) plus the
area-chair style. The chat-model vocabulary and response schemas live in
``domain/models/chat.py``."""
from enum import StrEnum
from pydantic import BaseModel, SerializeAsAny
from typing import Any

from domain.models.chat import ChatModelName, ChatModelResponseSchema


class AgentRole(StrEnum):
    """Prompt-versioning roles; the three reviewers share the single 'reviewer' role."""
    CHAT_AGENT = "chat"
    REVIEWER = "reviewer"
    META_REVIEWER = "meta_reviewer"
    AREA_CHAIR = "area_chair"
    AUTHOR_AGENT = "author_agent"


class ContextMode(StrEnum):
    """The retrieval strategy that built / serves an index."""
    FULL_CONTEXT = "full_context"
    """Whole paper, all sections concatenated — no query."""
    BM25 = "bm25"
    """Chunk the paper, rank chunks by BM25 lexical score against the query."""
    EMBEDDING = "embedding"
    """Chunk the paper, rank chunks by embedding cosine similarity to the query."""
    NONE = "none"
    """The agent has no access to the context (e.g. a paper)."""


class AgentRequestContext(BaseModel):
    context_mode: ContextMode = ContextMode.NONE
    """The context mode used to retrieve the context for this agent"""
    retrieval_context_query: str | None = None    
    """The query used to retrieve the context for this agent. If it is not None, it contains the relevant query."""
    
    def default_none_context() -> "AgentRequestContext":
        return AgentRequestContext(context_mode=ContextMode.NONE, retrieval_context_query=None)
    
    @staticmethod
    def default_full_context() -> "AgentRequestContext":
        return AgentRequestContext(context_mode=ContextMode.FULL_CONTEXT, retrieval_context_query=None)


class AgentSystemPromptRequest(BaseModel):
    base_prompt_version: str
    focus_id: str 
    commitment_id: str 
    intention_id: str
    knowledgeability_id: str 
    style_id: str 


class CreateAgentRequest(BaseModel):
    """Request to create an agent with a specific role, model, temperature, and optional system prompt."""
    model: ChatModelName
    temperature: float
    agent_role: AgentRole
    agent_index: int | None = None
    prompt_version: str | None = None
    paper_id: str | None = None    
    context: AgentRequestContext = AgentRequestContext.default_none_context()
    prompt_request: AgentSystemPromptRequest | None = None
    retrieval_context_query: str | None = None    


class AgentResponse(BaseModel):
    """An agent's structured payload plus the token usage and traces of how it
    was produced."""
    agent_role: AgentRole
    agent_index: int | None = None
    
    response_schema: SerializeAsAny[ChatModelResponseSchema]
    
    system_prompt: str | None = None
    input_message: str | None = None
    context_used: str | None = None
    
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    
    def to_json(self) -> str:
        return self.model_dump_json(ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()