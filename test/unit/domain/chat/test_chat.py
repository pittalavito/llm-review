"""Unit tests for the chat layer (domain/chat/base.py) — Factory, Adapter, the
Chat facade and structured/raw invocation — exercised through MockChat so no
real LLM call is made."""
import pytest
from langchain_core.messages import AIMessage

from core.error import ValidationError
from domain.chat.base import Adapter, Chat, ChatResponse, Factory, MockChat
from models.domain.chat import (
    ChatFallbackRawResponseSchema,
    ChatModelName,
    MetaReviewResponseSchema,
    ReviewerResponseSchema,
)


class Utils:
    """Static test helpers for the chat tests."""

    @staticmethod
    def ai_message(content: str = "hi", tokens: tuple[int, int, int] | None = (100, 50, 150)) -> AIMessage:
        usage = None if tokens is None else {"input_tokens": tokens[0], "output_tokens": tokens[1], "total_tokens": tokens[2]}
        return AIMessage(content=content, usage_metadata=usage)


class TestFactory:
    def test_create_chat_message_binds_system_and_message(self):
        template = Factory.create_chat_message("SYSTEM")
        rendered = template.format_messages(context="CTX ", message="MSG")
        assert rendered[0].content == "SYSTEM"
        assert rendered[1].content == "CTX MSG"

    def test_create_chat_variables_defaults_missing_context(self):
        assert Factory.create_chat_variables("m", None) == {"message": "m", "context": ""}
        assert Factory.create_chat_variables("m", "c") == {"message": "m", "context": "c"}

    def test_create_chat_mock(self):
        chat = Factory.create_chat(ChatModelName.MOCK, 0.0)
        assert isinstance(chat, MockChat)
        assert chat._chat_model is None  # the mock has no provider client


class TestAdapter:
    def test_ai_message_becomes_fallback_with_tokens(self):
        result = Adapter.to_chat_response_ai_message(Utils.ai_message("raw text"))
        assert isinstance(result.response_schema, ChatFallbackRawResponseSchema)
        assert result.response_schema.response == "raw text"
        assert (result.input_tokens, result.output_tokens, result.total_tokens) == (100, 50, 150)

    def test_dict_keeps_parsed_schema_and_extracts_tokens(self):
        parsed = ReviewerResponseSchema(
            summary="s", significance_and_novelty="n", reasons_for_acceptance=["a"], rating=6, confidence=4,
            soundness=3, presentation=2, contribution=3,
        )
        result = Adapter.to_chat_response_dict({"parsed": parsed, "raw": Utils.ai_message(), "parsing_error": None})
        assert result.response_schema is parsed
        assert (result.input_tokens, result.total_tokens) == (100, 150)

    def test_dict_rejects_non_dict(self):
        with pytest.raises(ValidationError):
            Adapter.to_chat_response_dict("not a dict")

    def test_missing_usage_metadata_yields_none_tokens(self):
        result = Adapter.to_chat_response_ai_message(Utils.ai_message(tokens=None))
        assert result.input_tokens is None
        assert result.total_tokens is None


class TestChatFacade:
    def test_invoke_without_schema_returns_raw_fallback(self):
        result = MockChat().invoke("sys", "hello")
        assert isinstance(result, ChatResponse)
        assert isinstance(result.response_schema, ChatFallbackRawResponseSchema)

    def test_invoke_with_schema_returns_parsed_and_estimated_tokens(self):
        result = MockChat().invoke("sys", "review", response_schema=ReviewerResponseSchema)
        assert isinstance(result.response_schema, ReviewerResponseSchema)
        assert result.response_schema.rating == 6
        assert result.input_tokens > 0 and result.output_tokens > 0
        assert result.total_tokens == result.input_tokens + result.output_tokens

    def test_invoke_dispatches_by_schema_type(self):
        result = MockChat().invoke("sys", "meta", response_schema=MetaReviewResponseSchema)
        assert isinstance(result.response_schema, MetaReviewResponseSchema)

    def test_empty_message_still_parses(self):
        # the facade itself does not validate emptiness (that's the agent's job)
        result = MockChat().invoke("sys", "", response_schema=ReviewerResponseSchema)
        assert isinstance(result.response_schema, ReviewerResponseSchema)
