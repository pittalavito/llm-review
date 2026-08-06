"""Chat-model domain models: the supported model identifiers and the structured
output schemas each agent produces (reviewer, meta-review, area-chair, author).
Agent identity/persona and the ``AgentResponse`` wrapper live in
``domain/models/agent.py``."""
from enum import StrEnum
from pydantic import BaseModel, Field

from models.domain import ranges


class ChatModelName(StrEnum):
    """Supported LLM model identifiers, grouped by provider."""
    MOCK = "mock"
    OLLAMA_TINYLLAMA = "tinyllama:1.1b"
    OLLAMA_LLAMA32 = "llama3.2:3b"
    OLLAMA_GROQ_TOOL_USE = "llama3-groq-tool-use"
    OLLAMA_GEMMA_4 = "gemma4"
    OLLAMA_GEMMA_3_4B = "gemma3:4b"
    OLLAMA_MISTRAL_7B = "mistral:7b"
    OPENAI_GPT4O = "gpt-4o"
    OPENAI_GPT4O_MINI = "gpt-4o-mini"
    ANTHROPIC_CLAUDE_SONNET = "claude-sonnet-4-6"
    ANTHROPIC_CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
    OTHER_LLM_PROVIDER_QWEN_3_6 = "qwen3.6:27b"

    def is_mock(self) -> bool:
        return self in {
            self.MOCK
        }
    
    def is_ollama(self) -> bool:
        return self in {
            self.OLLAMA_TINYLLAMA,
            self.OLLAMA_LLAMA32,
            self.OLLAMA_GROQ_TOOL_USE,
            self.OLLAMA_GEMMA_4,
            self.OLLAMA_GEMMA_3_4B,
            self.OLLAMA_MISTRAL_7B
        }

    def is_openai(self) -> bool:
        return self in {
            self.OPENAI_GPT4O,
            self.OPENAI_GPT4O_MINI
        }

    def is_anthropic(self) -> bool:
        return self in {
            self.ANTHROPIC_CLAUDE_SONNET,
            self.ANTHROPIC_CLAUDE_HAIKU
        }

    def is_other_llm_provider(self) -> bool:
        return self == self.OTHER_LLM_PROVIDER_QWEN_3_6


class ChatReviewDecision(StrEnum):
    """The recommendation / decision produced by the review agents."""
    ACCEPT = "accept"
    MINOR_REVISION = "minor_revision"
    REJECT = "reject"


class ChatRevisedSection(BaseModel):
    """A single revised paper section produced by the author."""
    section_name: str
    content: str


class ChatReviewerRebuttal(BaseModel):
    """Targeted rebuttal addressed to a specific reviewer."""
    reviewer_name: str
    """The target reviewer, e.g. ``reviewer_1``."""
    response: str = Field(min_length=1, max_length=1_000)


class ChatModelResponseSchema(BaseModel):
    """Base class for chat model structured output schemas. Each agent's structured payload inherits from this base class."""
    pass


class ChatFallbackRawResponseSchema(ChatModelResponseSchema):
    """Fallback payload for agents without a structured output schema."""
    response: str


class ReviewerResponseSchema(ChatModelResponseSchema):
    """Unified review aligned with the OpenReview form: summary, arguments,
    the overall rating/confidence and the numeric sub-scores (soundness,
    presentation, contribution) human reviewers also fill in — so graph
    reviews and OpenReview reviews are comparable score-for-score."""
    summary: str = Field(min_length=1, max_length=600)
    significance_and_novelty: str = Field(min_length=1, max_length=300)
    reasons_for_acceptance: list[str] = Field(min_length=1, max_length=4)
    reasons_for_rejection: list[str] = Field(default_factory=list, max_length=4)
    suggestions: list[str] = Field(default_factory=list, max_length=4)
    rating: int = Field(ge=ranges.RATING[0], le=ranges.RATING[1])
    confidence: int = Field(ge=ranges.CONFIDENCE[0], le=ranges.CONFIDENCE[1])
    soundness: int = Field(ge=ranges.SUBSCORE[0], le=ranges.SUBSCORE[1])
    presentation: int = Field(ge=ranges.SUBSCORE[0], le=ranges.SUBSCORE[1])
    contribution: int = Field(ge=ranges.SUBSCORE[0], le=ranges.SUBSCORE[1])


class MetaReviewResponseSchema(ChatModelResponseSchema):
    """Aggregates the three reviews into a summary and recommendation for the Area Chair."""
    summary: str = Field(min_length=1, max_length=600)
    key_points: list[str] = Field(min_length=1, max_length=5)
    overall_score: int = Field(ge=ranges.SCORE[0], le=ranges.SCORE[1])
    recommendation: ChatReviewDecision


class AreaChairResponseSchema(ChatModelResponseSchema):
    """Final binding decision produced by the Area Chair after reading reviews and meta-review."""
    summary: str = Field(min_length=1, max_length=400)
    justification: str = Field(min_length=1, max_length=400)
    decision: ChatReviewDecision
    confidence: int = Field(ge=ranges.CONFIDENCE[0], le=ranges.CONFIDENCE[1])


class AuthorResponseSchema(ChatModelResponseSchema):
    """Author's rebuttal, per-reviewer targeted responses, and revised paper sections."""
    rebuttal: str = Field(min_length=1, max_length=600)
    reviewer_rebuttals: list[ChatReviewerRebuttal] = Field(default_factory=list)
    revised_sections: list[ChatRevisedSection] = Field(default_factory=list, max_length=3)
    key_changes: list[str] = Field(min_length=1, max_length=5)
