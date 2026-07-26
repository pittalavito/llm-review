"""Unit tests for the agent layer (domain/agent/agent.py) — message
normalization, the Adapter (ChatResponse -> AgentResponse), the Agent.run flow
and the concrete agents' identity/schema — exercised through MockChatModel
wrapped in a Chat, so no real LLM call is made."""
import pytest
from langchain_core.messages import AIMessage

from core.error import UpstreamError, ValidationError
from domain.agent.base import Adapter, Agent, AreaChairAgent, AuthorAgent, MetaReviewerAgent, ReviewerAgent
from domain.chat.base import Chat, ChatResponse
from domain.chat.mock_chat import MockChatModel
from domain.models.agent import AgentResponse, AgentRole
from domain.models.chat import (
    AreaChairResponseSchema,
    AuthorResponseSchema,
    MetaReviewResponseSchema,
    ReviewerResponseSchema,
)


class Utils:
    """Static test helpers for the agent tests."""

    @staticmethod
    def chat() -> Chat:
        return Chat(MockChatModel())

    @staticmethod
    def chat_response() -> ChatResponse:
        response_schema = ReviewerResponseSchema(
            summary="s", 
            significance_and_novelty="n", 
            reasons_for_acceptance=["a"], 
            rating=6, 
            confidence=4
        )
        
        raw = AIMessage(content="x")
        return ChatResponse(
            response_schema=response_schema,
            raw=raw,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )


class _BoomChat:
    """A Chat stand-in whose invoke always fails, to test upstream wrapping."""

    def invoke(self, *args, **kwargs):
        raise RuntimeError("boom")


class TestNormalizeMessage:
    def test_strips_surrounding_whitespace(self):
        assert Agent._normalize_message("  hello  ") == "hello"

    def test_empty_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Agent._normalize_message("   ")


class TestAdapter:
    def test_to_agent_response_maps_fields_and_tokens(self):
        chat_response = Utils.chat_response()
        result = Adapter.to_agent_response(AgentRole.REVIEWER, 1, "msg", "ctx", chat_response)
        assert isinstance(result, AgentResponse)
        assert result.agent_role is AgentRole.REVIEWER and result.agent_index == 1
        assert result.response_schema is chat_response.response_schema
        assert result.input_message == "msg"
        assert result.context_used == "ctx"
        assert (result.input_tokens, result.output_tokens, result.total_tokens) == (100, 50, 150)

    def test_to_agent_response_leaves_traces_empty(self):
        result = Adapter.to_agent_response(AgentRole.AUTHOR_AGENT, None, "m", None, Utils.chat_response())
        assert result.prompt_trace is None
        assert result.runtime_trace is None
        assert result.context_used is None


class TestAgentRun:
    def test_run_returns_agent_response_with_parsed_schema_and_tokens(self):
        result = ReviewerAgent(Utils.chat()).run("  review this paper  ")
        assert isinstance(result, AgentResponse)
        assert isinstance(result.response_schema, ReviewerResponseSchema)
        assert result.agent_role is AgentRole.REVIEWER and result.agent_index == 1
        assert result.input_message == "review this paper"  # normalized
        assert result.context_used is None  # default _retrieve_context
        assert (result.input_tokens, result.output_tokens, result.total_tokens) == (100, 50, 150)

    def test_run_empty_message_raises_before_chat(self):
        with pytest.raises(ValidationError):
            ReviewerAgent(Utils.chat()).run("   ")

    def test_run_wraps_chat_failure_in_upstream_error(self):
        with pytest.raises(UpstreamError):
            ReviewerAgent(_BoomChat()).run("review this paper")


class TestConcreteAgents:
    @pytest.mark.parametrize(
        "agent_cls, expected_role, expected_index, expected_name, expected_schema",
        [
            (ReviewerAgent, AgentRole.REVIEWER, 1, "reviewer_1", ReviewerResponseSchema),
            (MetaReviewerAgent, AgentRole.META_REVIEWER, None, "meta_reviewer", MetaReviewResponseSchema),
            (AreaChairAgent, AgentRole.AREA_CHAIR, None, "area_chair", AreaChairResponseSchema),
            (AuthorAgent, AgentRole.AUTHOR_AGENT, None, "author_agent", AuthorResponseSchema),
        ],
    )
    def test_identity_and_run_schema(self, agent_cls, expected_role, expected_index, expected_name, expected_schema):
        agent = agent_cls(Utils.chat())
        assert agent.agent_role is expected_role
        assert agent.agent_index == expected_index
        assert agent.name == expected_name
        assert agent.response_schema is expected_schema
        result = agent.run("do your job")
        assert result.agent_role is expected_role
        assert result.agent_index == expected_index
        assert isinstance(result.response_schema, expected_schema)

    def test_reviewer_index_is_unbounded(self):
        # not tied to 3: any reviewer index is a valid, distinct agent
        agent = ReviewerAgent(Utils.chat(), index=5)
        assert agent.name == "reviewer_5"
        assert agent.agent_index == 5
        assert agent.run("go").agent_index == 5
