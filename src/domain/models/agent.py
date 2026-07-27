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


class AgentContext(BaseModel):
    context_mode: ContextMode = ContextMode.NONE
    """The context mode used to retrieve the context for this agent"""
    retrieval_context_query: str | None = None    
    """The query used to retrieve the context for this agent. If it is not None, it contains the relevant query."""
    
    def default_none_context() -> "AgentContext":
        return AgentContext(context_mode=ContextMode.NONE, retrieval_context_query=None)
    
    @staticmethod
    def default_full_context() -> "AgentContext":
        return AgentContext(context_mode=ContextMode.FULL_CONTEXT, retrieval_context_query=None)


class CreateAgentRequest(BaseModel):
    """Request to create an agent with a specific role, model, temperature, and optional system prompt."""
    model: ChatModelName
    temperature: float
    agent_role: AgentRole
    agent_index: int | None = None
    prompt_version: str | None = None
    paper_id: str | None = None    
    context_mode: ContextMode = ContextMode.NONE
    retrieval_context_query: str | None = None


class ReviewerFocus(StrEnum):
    """Primary evaluation angle assigned to a reviewer.
    Each reviewer covers a different dimension of the paper so that
    the three reviews are complementary rather than redundant.
    """

    SOUNDNESS = "soundness"
    """Theoretical correctness, proofs, assumptions."""
    EMPIRICAL = "empirical"
    """Experiments, baselines, reproducibility."""
    NOVELTY = "novelty"
    """Originality, related work, impact."""


class ReviewerCommitment(StrEnum):
    """How diligently the reviewer engages with the paper."""
    RESPONSIBLE = "responsible"
    IRRESPONSIBLE = "irresponsible"


class ReviewerIntention(StrEnum):
    """Whether the reviewer acts in good or bad faith."""
    BENIGN = "benign"
    MALICIOUS = "malicious"


class ReviewerKnowledgeability(StrEnum):
    """The reviewer's expertise on the paper's topic."""
    KNOWLEDGEABLE = "knowledgeable"
    UNKNOWLEDGEABLE = "unknowledgeable"


class ReviewerPersona(BaseModel):
    """The persona axes that shape a reviewer's behavior."""
    commitment: ReviewerCommitment = ReviewerCommitment.RESPONSIBLE
    intention: ReviewerIntention = ReviewerIntention.BENIGN
    knowledgeability: ReviewerKnowledgeability = ReviewerKnowledgeability.KNOWLEDGEABLE
    focus: ReviewerFocus = ReviewerFocus.SOUNDNESS


class AreaChairStyle(StrEnum):
    """The decision style adopted by the Area Chair."""
    AUTHORITARIAN = "authoritarian"
    CONFORMIST = "conformist"
    INCLUSIVE = "inclusive"

class AgentResponse(BaseModel):
    """An agent's structured payload plus the token usage and traces of how it
    was produced."""
    agent_role: AgentRole
    agent_index: int | None = None
    response_schema: SerializeAsAny[ChatModelResponseSchema]
    input_message: str | None = None
    context_used: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    prompt_trace: dict[str, Any] | None = None
    runtime_trace: dict[str, Any] | None = None

    def to_json(self) -> str:
        return self.model_dump_json(ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()