"""Unit tests for the chat layer (domain/chat/base.py) — Factory, Adapter, the
Chat facade, structured/raw invocation and the two-phase tool loop — exercised
through MockChat / duck-typed fake models so no real LLM call is made."""
import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from core.error import ValidationError
from domain.chat.base import Adapter, Chat, ChatResponse, Factory, MockChat
from models.domain.chat import (
    ChatFallbackRawResponseSchema,
    ChatModelName,
    MetaReviewResponseSchema,
    ReviewerResponseSchema,
)


def _review_instance() -> ReviewerResponseSchema:
    return ReviewerResponseSchema(
        summary="s", significance_and_novelty="n", reasons_for_acceptance=["a"],
        rating=6, confidence=4, soundness=3, presentation=2, contribution=3,
    )


def _search_tool(calls: list[str]):
    @tool("search_paper")
    def search_paper(query: str) -> str:
        """Search the paper under review."""
        calls.append(query)
        return f"passage for {query}"
    return search_paper


class FakeToolModel:
    """Duck-typed chat model for the tool loop: emits ``rounds`` tool-calling
    turns (then a plain turn), and parses on the final structured call."""

    def __init__(self, rounds: int = 1):
        self.rounds = rounds
        self.loop_invocations = 0
        self.structured_invocations = 0
        self.final_messages = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.loop_invocations += 1
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        if self.loop_invocations <= self.rounds:
            return AIMessage(content="", usage_metadata=usage, tool_calls=[
                {"name": "search_paper", "args": {"query": f"q{self.loop_invocations}"}, "id": f"call_{self.loop_invocations}", "type": "tool_call"},
            ])
        return AIMessage(content="done", usage_metadata=usage)

    def with_structured_output(self, schema, include_raw=True):
        model = self

        class _Structured:
            def invoke(self, messages):
                model.structured_invocations += 1
                model.final_messages = messages
                raw = AIMessage(content="", usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30})
                return {"parsed": _review_instance(), "raw": raw, "parsing_error": None}

        return _Structured()


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


class TestToolLoop:
    def test_executes_tools_and_returns_the_structured_payload(self):
        calls: list[str] = []
        model = FakeToolModel(rounds=1)
        chat = Chat(model, model_name=ChatModelName.OPENAI_GPT4O_MINI)
        result = chat.invoke("sys", "review it", response_schema=ReviewerResponseSchema, tools=[_search_tool(calls)])

        assert calls == ["q1"]  # the tool ran with the model's arguments
        assert isinstance(result.response_schema, ReviewerResponseSchema)
        assert result.tool_trace is not None and len(result.tool_trace) == 1
        record = result.tool_trace[0]
        assert record.tool_name == "search_paper"
        assert record.arguments == {"query": "q1"}
        assert record.result == "passage for q1"
        # transcript handed to the final call carries the tool exchange
        assert any(isinstance(m, ToolMessage) for m in model.final_messages)

    def test_tokens_are_accumulated_across_all_turns(self):
        model = FakeToolModel(rounds=1)
        chat = Chat(model, model_name=ChatModelName.OPENAI_GPT4O_MINI)
        result = chat.invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=[_search_tool([])])
        # 2 loop turns (tool call + no-tool break) at 10/5/15 each + final 20/10/30
        assert (result.input_tokens, result.output_tokens, result.total_tokens) == (40, 20, 60)

    def test_max_tool_iterations_caps_the_loop(self):
        model = FakeToolModel(rounds=10)  # would call tools forever
        chat = Chat(model, model_name=ChatModelName.OPENAI_GPT4O_MINI)
        result = chat.invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=[_search_tool([])], max_tool_iterations=2)
        assert model.loop_invocations == 2  # stopped at the cap
        assert model.structured_invocations == 1  # still forced to answer
        assert len(result.tool_trace) == 2

    def test_tool_errors_are_recorded_not_raised(self):
        @tool("search_paper")
        def broken(query: str) -> str:
            """Always fails."""
            raise RuntimeError("index unavailable")

        chat = Chat(FakeToolModel(rounds=1), model_name=ChatModelName.OPENAI_GPT4O_MINI)
        result = chat.invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=[broken])
        assert isinstance(result.response_schema, ReviewerResponseSchema)  # invocation survived
        assert "Error executing tool" in result.tool_trace[0].result

    def test_unsupported_model_fails_fast(self):
        chat = Chat(FakeToolModel(), model_name=ChatModelName.OLLAMA_GEMMA_3_4B)
        with pytest.raises(ValidationError, match="does not support tool calling"):
            chat.invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=[_search_tool([])])

    def test_no_tools_keeps_the_plain_path(self):
        # the fake model has no ChatPromptTemplate support: reaching it would fail,
        # so a None/empty tools list must not enter the tool loop
        result = MockChat().invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=None)
        assert result.tool_trace is None


class TestMockChatTools:
    def test_mock_executes_the_first_tool_and_records_it(self):
        calls: list[str] = []
        result = MockChat().invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=[_search_tool(calls)])
        assert isinstance(result.response_schema, ReviewerResponseSchema)  # canned payload as usual
        assert calls == ["methodology results evaluation"]  # tool really executed
        assert result.tool_trace is not None and result.tool_trace[0].result == "passage for methodology results evaluation"

    def test_mock_records_tool_failures(self):
        @tool("search_paper")
        def broken(query: str) -> str:
            """Always fails."""
            raise RuntimeError("no redis here")

        result = MockChat().invoke("sys", "m", response_schema=ReviewerResponseSchema, tools=[broken])
        assert "Error executing tool" in result.tool_trace[0].result
