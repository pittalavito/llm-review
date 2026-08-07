"""Unit tests for the agent domain models (models/domain/agent.py):
AgentRequestContext defaults, retrieval-tool knob bounds, and the SUMMARY
context mode round-trip."""
import pytest
from pydantic import ValidationError

from models.domain.agent import AgentRequestContext, ContextMode


class TestAgentRequestContext:
    def test_defaults(self):
        context = AgentRequestContext()
        assert context.context_mode == ContextMode.NONE
        assert context.retrieval_context_query is None
        assert context.use_retrieval_tool is False
        assert context.retrieval_top_k == 5
        assert context.max_tool_iterations == 3

    def test_summary_mode_round_trips(self):
        context = AgentRequestContext(context_mode="summary")
        assert context.context_mode == ContextMode.SUMMARY
        restored = AgentRequestContext.model_validate_json(context.model_dump_json())
        assert restored == context

    def test_tool_fields_round_trip(self):
        context = AgentRequestContext(use_retrieval_tool=True, retrieval_top_k=10, max_tool_iterations=5)
        restored = AgentRequestContext.model_validate(context.model_dump())
        assert restored.use_retrieval_tool is True
        assert restored.retrieval_top_k == 10
        assert restored.max_tool_iterations == 5

    @pytest.mark.parametrize("top_k", [0, 21])
    def test_top_k_out_of_bounds_rejected(self, top_k):
        with pytest.raises(ValidationError):
            AgentRequestContext(retrieval_top_k=top_k)

    @pytest.mark.parametrize("iterations", [0, 11])
    def test_max_tool_iterations_out_of_bounds_rejected(self, iterations):
        with pytest.raises(ValidationError):
            AgentRequestContext(max_tool_iterations=iterations)
