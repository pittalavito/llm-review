"""Unit tests for the review graph: an end-to-end run over MockChatModel with an
arbitrary committee size (no LLM, no DB) and the two conditional-edge functions.
GraphService no longer builds agents or persists runs — those are the caller's job."""
import pytest

from core.error import ConflictError
from domain.agent.base import Factory as AgentFactory
from domain.chat.base import Chat
from domain.chat.mock_chat import MockChatModel
from domain.graph.base import Nodes
from domain.models.agent import AgentRole
from domain.models.chat import ChatReviewDecision
from domain.models.graph import GraphConfig
from service.graph_service import GraphService


def _agents(num_reviewers: int) -> dict:
    chat = Chat(MockChatModel())
    agents = {}
    for index in range(1, num_reviewers + 1):
        agent = AgentFactory.create_agent(AgentRole.REVIEWER, chat, agent_index=index)
        agents[agent.name] = agent
    for role in (AgentRole.META_REVIEWER, AgentRole.AREA_CHAIR, AgentRole.AUTHOR_AGENT):
        agent = AgentFactory.create_agent(role, chat)
        agents[agent.name] = agent
    return agents


class TestGraphRun:
    def test_runs_end_to_end_with_arbitrary_committee_size(self):
        n = 5  # not tied to 3
        config = GraphConfig.default_config(num_reviewers=n, max_rounds=1)
        service = GraphService(config=object())
        service.compile(_agents(n), config)

        result = service.invoke("/papers/p.pdf")

        assert len(result["reviews"]) == n  # every reviewer ran (fan-out)
        assert result["meta_review"] is not None
        assert result["area_chair_response"] is not None
        assert result["decision"] == ChatReviewDecision.MINOR_REVISION  # mock -> terminal
        assert result["author_response"] is None  # terminal decision, no revision round
        assert result["current_round"] == 1
        assert len(result["agent_runs"]) == n + 2  # N reviewers + meta + area chair

    def test_invoke_before_compile_raises(self):
        service = GraphService(config=object())
        with pytest.raises(ConflictError):
            service.invoke("/papers/p.pdf")


class TestConditionalEdges:
    def test_area_chair_terminates_on_accept_and_minor_revision(self):
        assert Nodes.area_chair_conditional({"decision": ChatReviewDecision.ACCEPT}) == "accept"
        assert Nodes.area_chair_conditional({"decision": ChatReviewDecision.MINOR_REVISION}) == "accept"

    def test_area_chair_revises_otherwise(self):
        assert Nodes.area_chair_conditional({"decision": ChatReviewDecision.MAJOR_REVISION}) == "revise"
        assert Nodes.area_chair_conditional({"decision": None}) == "revise"

    def test_end_loop_ends_when_rounds_exhausted(self):
        assert Nodes.end_loop_conditional({"current_round": 1, "max_rounds": 1}) == "end"

    def test_end_loop_continues_while_rounds_remain(self):
        assert Nodes.end_loop_conditional({"current_round": 1, "max_rounds": 3}) == "loop"
