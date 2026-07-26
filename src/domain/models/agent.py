"""Agent identity and persona domain models: the agent roles/names and the
reviewer persona axes (focus, commitment, intention, knowledgeability) plus the
area-chair style. The chat-model vocabulary and response schemas live in
``domain/models/chat.py``."""
from enum import StrEnum
from pydantic import BaseModel
from typing import Any

from domain.models.chat import ChatModelResponseSchema

class AgentRole(StrEnum):
    """Prompt-versioning roles; the three reviewers share the single 'reviewer' role."""
    REVIEWER = "reviewer"
    META_REVIEWER = "meta_reviewer"
    AREA_CHAIR = "area_chair"
    AUTHOR_AGENT = "author_agent"


class AgentName(StrEnum):
    """The concrete agents in the review graph."""
    REVIEWER_1 = "reviewer_1"
    REVIEWER_2 = "reviewer_2"
    REVIEWER_3 = "reviewer_3"
    META_REVIEWER = "meta_reviewer"
    AREA_CHAIR = "area_chair"
    AUTHOR_AGENT = "author_agent"

    @classmethod
    def reviewers(cls) -> frozenset["AgentName"]:
        """The reviewer agents that share the single 'reviewer' base template."""
        return frozenset({cls.REVIEWER_1, cls.REVIEWER_2, cls.REVIEWER_3})

    def is_reviewer(self) -> bool:
        return self in self.reviewers()

    def role(self) -> str:
        """Prompt-versioning role: the three reviewers share one base template."""
        return AgentRole.REVIEWER if self.is_reviewer() else str(self)


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
    agent: AgentName
    response_schema: ChatModelResponseSchema
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