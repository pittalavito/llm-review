"""Unit tests for the review graph itself (domain/graph/review.py): an end-to-end
run over MockChat with an arbitrary committee size (no LLM, no DB) driven via
GraphReview, plus the two conditional-edge methods and the individual node
classes (message building + state update on both the happy path and the
schema-is-None / agent-failure path). Orchestration/persistence live in
GraphReviewService and are not exercised here."""
import pytest

from domain.agent.base import Factory as AgentFactory
from domain.chat.base import MockChat
from domain.graph.review import AreaChairNode, AuthorNode, GraphReview, MetaReviewerNode, ReviewerNode
from models.domain.agent import AgentRole, CreateAgentRequest
from models.domain.chat import ChatModelName, ChatReviewDecision
from models.domain.graph import CreateGraphReviewRequest, GraphReviewConfig
from models.domain.run_record import AgentResponseRecord


def _agents(num_reviewers: int) -> dict:
    chat = MockChat()

    def make(role: AgentRole, index: int | None = None):
        request = CreateAgentRequest(paper_id="other_p_pdf", model=ChatModelName.MOCK, temperature=0.0, agent_role=role, agent_index=index, prompt_preset_id=0)
        return AgentFactory.create_agent(request, chat, system_prompt=f"You are the {role}.")

    agents = {}
    for index in range(1, num_reviewers + 1):
        agent = make(AgentRole.REVIEWER, index)
        agents[agent.name] = agent
    for role in (AgentRole.META_REVIEWER, AgentRole.AREA_CHAIR, AgentRole.AUTHOR_AGENT):
        agent = make(role)
        agents[agent.name] = agent
    return agents


def _run(agents: dict, paper_id: str, max_rounds: int) -> dict:
    graph = GraphReview()
    graph.compile(agents)
    request = CreateGraphReviewRequest(
        paper_id=paper_id,
        graph_config=GraphReviewConfig.default_config(max_rounds=max_rounds),
    )
    return graph.invoke(graph.build_initial_state(request))


class TestGraphRun:
    def test_runs_end_to_end_with_arbitrary_committee_size(self):
        n = 5  # not tied to 3
        result = _run(_agents(n), "/papers/p.pdf", max_rounds=1)

        # Mock decision is minor_revision: only ACCEPT is terminal, so the
        # author writes one revision round before the rounds run out.
        assert len(result["reviews_response"]) == n  # every reviewer ran (fan-out)
        assert all(isinstance(review, dict) for review in result["reviews_response"])  # dicts, not JSON strings
        assert result["meta_review_response"] is not None
        assert result["area_chair_response"] is not None
        assert result["decision"] == ChatReviewDecision.MINOR_REVISION
        assert result["author_response"] is not None  # revision round happened
        assert result["revised_sections"]  # extracted from the author payload
        assert result["current_round"] == 1
        assert len(result["agent_records"]) == n + 3  # N reviewers + meta + area chair + author


class TestConditionalEdges:
    _graph = GraphReview()

    def test_area_chair_terminates_only_on_accept(self):
        assert self._graph._route_after_area_chair({"decision": ChatReviewDecision.ACCEPT}) == "accept"

    def test_area_chair_revises_otherwise(self):
        assert self._graph._route_after_area_chair({"decision": ChatReviewDecision.MINOR_REVISION}) == "revise"
        assert self._graph._route_after_area_chair({"decision": ChatReviewDecision.REJECT}) == "revise"

    def test_area_chair_fails_when_no_decision(self):
        assert self._graph._route_after_area_chair({"decision": None}) == "fail"

    def test_end_loop_ends_when_rounds_exhausted(self):
        assert self._graph._route_after_author({"author_response": {"rebuttal": "r"}, "current_round": 1, "max_rounds": 1}) == "end"

    def test_end_loop_continues_while_rounds_remain(self):
        assert self._graph._route_after_author({"author_response": {"rebuttal": "r"}, "current_round": 1, "max_rounds": 3}) == "loop"

    def test_author_routing_fails_when_no_author_response(self):
        assert self._graph._route_after_author({"author_response": None, "current_round": 1, "max_rounds": 3}) == "fail"


def _record(agent_role: AgentRole) -> AgentResponseRecord:
    """A minimal AgentResponseRecord — only its presence in the returned state
    delta is checked in these node tests, not its content."""
    return AgentResponseRecord(round=0, agent_role=agent_role, response_payload={})


class TestReviewerNode:
    def test_set_message_first_round_is_generic(self):
        node = ReviewerNode(next(iter(_agents(1).values())))
        message = node.set_message({"revised_sections": None})
        assert "produce your structured assessment" in message

    def test_set_message_round_two_includes_rebuttal_and_sections(self):
        node = ReviewerNode(next(iter(_agents(1).values())))
        state = {
            "revised_sections": {"Intro": "new content"},
            "author_response": {"rebuttal": "we addressed your concerns"},
        }
        message = node.set_message(state)
        assert "we addressed your concerns" in message
        assert "## Intro\nnew content" in message

    def test_set_message_round_two_defaults_rebuttal_when_missing(self):
        node = ReviewerNode(next(iter(_agents(1).values())))
        state = {"revised_sections": {"Intro": "new content"}, "author_response": None}
        message = node.set_message(state)
        assert "(none)" in message

    def test_update_state_schema_none_keeps_existing_reviews(self):
        node = ReviewerNode(next(iter(_agents(1).values())))
        state = {"reviews_response": [{"summary": "existing"}]}
        delta = node.update_state(state, None, _record(AgentRole.REVIEWER))
        assert delta["reviews_response"] == [{"summary": "existing"}]
        assert len(delta["agent_records"]) == 1


class TestMetaReviewerNode:
    def test_update_state_schema_none_still_advances_round(self):
        node = MetaReviewerNode(next(iter(_agents(1).values())))
        delta = node.update_state({"current_round": 0}, None, _record(AgentRole.META_REVIEWER))
        assert delta["meta_review_response"] is None
        assert delta["current_round"] == 1


class TestAreaChairNode:
    def test_update_state_schema_none_clears_decision(self):
        agents = _agents(1)
        node = AreaChairNode(next(a for a in agents.values() if a.agent_role is AgentRole.REVIEWER))
        delta = node.update_state({}, None, _record(AgentRole.AREA_CHAIR))
        assert delta["area_chair_response"] is None
        assert delta["decision"] is None


class TestAuthorNode:
    def test_update_state_schema_none_clears_response_and_sections(self):
        agents = _agents(1)
        node = AuthorNode(next(a for a in agents.values() if a.agent_role is AgentRole.REVIEWER))
        delta = node.update_state({}, None, _record(AgentRole.AUTHOR_AGENT))
        assert delta["author_response"] is None
        assert delta["revised_sections"] is None


class TestRegisterNodes:
    def test_raises_without_at_least_one_reviewer(self):
        agents = {a.name: a for a in _agents(1).values() if a.agent_role is not AgentRole.REVIEWER}
        graph = GraphReview()
        with pytest.raises(ValueError, match="at least one reviewer"):
            graph.compile(agents)
