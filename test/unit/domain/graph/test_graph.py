"""Unit tests for the review graph itself (domain/graph/base.py): an end-to-end
run over MockChatModel with an arbitrary committee size (no LLM, no DB) driven via
Builder, plus the two conditional-edge functions. Orchestration/persistence live
in GraphService and are not exercised here."""
from domain.agent.base import Factory as AgentFactory
from domain.chat.base import Chat
from domain.chat.mock_chat import MockChatModel
from domain.graph.base import Builder, Nodes
from domain.models.agent import AgentRole, CreateAgentRequest
from domain.models.chat import ChatModelName, ChatReviewDecision


def _agents(num_reviewers: int) -> dict:
    chat = Chat(MockChatModel())

    def make(role: AgentRole, index: int | None = None):
        request = CreateAgentRequest(model=ChatModelName.MOCK, temperature=0.0, agent_role=role, agent_index=index)
        return AgentFactory.create_agent(request, chat, system_prompt=f"You are the {role}.")

    agents = {}
    for index in range(1, num_reviewers + 1):
        agent = make(AgentRole.REVIEWER, index)
        agents[agent.name] = agent
    for role in (AgentRole.META_REVIEWER, AgentRole.AREA_CHAIR, AgentRole.AUTHOR_AGENT):
        agent = make(role)
        agents[agent.name] = agent
    return agents


def _run(agents: dict, paper_path: str, max_rounds: int) -> dict:
    graph = Builder.build_graph(agents).compile()
    return graph.invoke(Builder.build_initial_state(paper_path, max_rounds))


class TestGraphRun:
    def test_runs_end_to_end_with_arbitrary_committee_size(self):
        n = 5  # not tied to 3
        result = _run(_agents(n), "/papers/p.pdf", max_rounds=1)

        assert len(result["reviews"]) == n  # every reviewer ran (fan-out)
        assert result["meta_review"] is not None
        assert result["area_chair_response"] is not None
        assert result["decision"] == ChatReviewDecision.MINOR_REVISION  # mock -> terminal
        assert result["author_response"] is None  # terminal decision, no revision round
        assert result["current_round"] == 1
        assert len(result["agent_runs"]) == n + 2  # N reviewers + meta + area chair


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
