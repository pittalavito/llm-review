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
    OPENROUTER_GPT4O = "openai/gpt-4o"
    OPENROUTER_GPT4O_MINI = "openai/gpt-4o-mini"
    OPENROUTER_GPT5 = "openai/gpt-5"
    OPENROUTER_CLAUDE_SONNET_45 = "anthropic/claude-sonnet-4.5"
    OPENROUTER_DEEPSEEK_V3 = "deepseek/deepseek-chat"

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
        return self in {
            self.OTHER_LLM_PROVIDER_QWEN_3_6,
            self.OPENROUTER_GPT4O,
            self.OPENROUTER_GPT4O_MINI,
            self.OPENROUTER_GPT5,
            self.OPENROUTER_CLAUDE_SONNET_45,
            self.OPENROUTER_DEEPSEEK_V3,
        }

    def supports_tools(self) -> bool:
        """Whether the model can be trusted with tool calling. Small local
        models (tinyllama, gemma) either ignore tools or emit malformed calls;
        selecting them with the retrieval tool fails fast instead."""
        return self not in {
            self.OLLAMA_TINYLLAMA,
            self.OLLAMA_GEMMA_4,
            self.OLLAMA_GEMMA_3_4B,
        }


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
    response: str = Field(min_length=1)


class ToolCallRecord(BaseModel):
    """One executed tool round-trip inside an agent invocation: what the model
    asked for and what the tool returned (result truncated at record time)."""
    tool_name: str
    arguments: dict
    result: str


_UNSUPPORTED_SCHEMA_KEYS = {
    "minLength", "maxLength", "minItems", "maxItems",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
}
"""JSON-schema constraint keywords rejected by some providers' structured
output validation (Anthropic accepts only the basic type/required subset)."""


def _strip_schema_constraints(schema):
    if isinstance(schema, dict):
        return {key: _strip_schema_constraints(value) for key, value in schema.items() if key not in _UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(schema, list):
        return [_strip_schema_constraints(item) for item in schema]
    return schema


class ChatModelResponseSchema(BaseModel):
    """Base class for chat model structured output schemas. Each agent's
    structured payload inherits from this base class. The emitted JSON schema
    is stripped of constraint keywords so it stays valid across providers;
    quantitative limits live in the prompts, ranges are still validated
    client-side on the parsed payload."""

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        return _strip_schema_constraints(super().model_json_schema(*args, **kwargs))


class ChatFallbackRawResponseSchema(ChatModelResponseSchema):
    """Fallback payload for agents without a structured output schema."""
    response: str


class SummaryResponseSchema(ChatModelResponseSchema):
    """Structured output of the paper summarizer (SUMMARY retrieval strategy)."""
    summary: str = Field(min_length=1)


class ReviewerResponseSchema(ChatModelResponseSchema):
    """Unified review aligned with the OpenReview form: summary, arguments,
    the overall rating/confidence and the numeric sub-scores (soundness,
    presentation, contribution) human reviewers also fill in — so graph
    reviews and OpenReview reviews are comparable score-for-score."""
    summary: str = Field(min_length=1)
    significance_and_novelty: str = Field(min_length=1)
    reasons_for_acceptance: list[str] = Field(min_length=1)
    reasons_for_rejection: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    rating: int = Field(ge=ranges.RATING[0], le=ranges.RATING[1])
    confidence: int = Field(ge=ranges.CONFIDENCE[0], le=ranges.CONFIDENCE[1])
    soundness: int = Field(ge=ranges.SUBSCORE[0], le=ranges.SUBSCORE[1])
    presentation: int = Field(ge=ranges.SUBSCORE[0], le=ranges.SUBSCORE[1])
    contribution: int = Field(ge=ranges.SUBSCORE[0], le=ranges.SUBSCORE[1])


class MetaReviewResponseSchema(ChatModelResponseSchema):
    """Aggregates the three reviews into a summary and recommendation for the Area Chair."""
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    overall_score: int = Field(ge=ranges.SCORE[0], le=ranges.SCORE[1])
    recommendation: ChatReviewDecision


class AreaChairResponseSchema(ChatModelResponseSchema):
    """Final binding decision produced by the Area Chair after reading reviews and meta-review."""
    summary: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    decision: ChatReviewDecision
    confidence: int = Field(ge=ranges.CONFIDENCE[0], le=ranges.CONFIDENCE[1])


class AuthorResponseSchema(ChatModelResponseSchema):
    """Author's rebuttal, per-reviewer targeted responses, and revised paper sections."""
    rebuttal: str = Field(min_length=1)
    reviewer_rebuttals: list[ChatReviewerRebuttal] = Field(default_factory=list)
    revised_sections: list[ChatRevisedSection] = Field(default_factory=list)
    key_changes: list[str] = Field(min_length=1)
