"""Self-contained graph layer: the review StateGraph and its collaborators —
one ``AgentNode`` subclass per role (the LangGraph node: builds the task
message from the state, runs the agent, returns the state delta), the two
routing functions for the conditional edges, and ``Builder`` (wires the graph
for an arbitrary number of reviewers).

START -> dispatch -> (reviewer_1 .. reviewer_N in parallel) -> meta_reviewer ->
area_chair --accept--> END / --revise--> author_agent --loop--> dispatch /
--end--> END. Reviewers are detected by role, so the committee size is whatever
set of agents is passed in. The paper text is not built here: it lives in the
agent's ``context`` (set at build time via the retrieval service).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from langgraph.graph import END, START, StateGraph

from domain.agent.base import Agent
from domain.graph.state import ReviewState

from domain.models.agent import AgentResponse, AgentRole
from domain.models.chat import ChatReviewDecision
from domain.models.run_record import AgentRun


_DISPATCH = "reviewers"
_META = "meta_reviewer"
_AREA_CHAIR = "area_chair"
_AUTHOR = "author_agent"


class AgentNode(ABC):
    """A LangGraph node bound to one agent. Calling the instance runs the full
    step: build the task message from the state, run the agent, record the
    ``AgentRun`` and return the state delta. Subclasses provide the two
    role-specific pieces as plain methods."""

    round_offset = 0
    """Correction for the recorded round, for roles that run after ``meta``
    already bumped ``current_round``."""

    def __init__(self, agent: Agent):
        self.agent = agent

    def __call__(self, state: ReviewState) -> dict:
        message = self.build_input_message(state)
        response = self.agent.run(message)
        run = self._build_run(state, message, response)
        return self.update_review_status(state, response, run)

    @abstractmethod
    def build_input_message(self, state: ReviewState) -> str:
        """The human message (the *task*) for this agent — never empty."""

    @abstractmethod
    def update_review_status(self, state: ReviewState, response: AgentResponse, run: AgentRun) -> dict:
        """The state delta produced by this agent's response."""

    def _build_run(self, state: ReviewState, message: str, response: AgentResponse) -> AgentRun:
        return AgentRun(
            agent_role=response.agent_role,
            agent_index=response.agent_index,
            round=state["current_round"] + self.round_offset,
            input_message=response.input_message or message,
            context_used=response.context_used,
            response_payload=response.response_schema.model_dump(),
            prompt_trace=response.prompt_trace,
            runtime_trace={
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
            },
        )


class ReviewerNode(AgentNode):

    def build_input_message(self, state: ReviewState) -> str:
        revised = state.get("revised_sections")
        if not revised:
            return "Review the paper provided in your context and produce your structured assessment."

        # TODO rivedere flusso 2
        # Round 2: re-review with the author's response (paper still in context).
        rebuttal = (state.get("author_response") or {}).get("rebuttal") or "(none)"
        sections = "\n\n".join(f"## {name}\n{content}" for name, content in revised.items())
        return (
            "Re-review the paper. The authors submitted a rebuttal and revised sections — "
            "update your assessment, stating whether your concerns were addressed.\n\n"
            f"Author rebuttal:\n{rebuttal}\n\n"
            f"Revised sections:\n{sections}"
        )

    def update_review_status(self, state: ReviewState, response: AgentResponse, run: AgentRun) -> dict:
        return {
            "reviews": [response.response_schema.model_dump_json()], 
            "agent_runs": [run.model_dump()]
        }


class MetaReviewerNode(AgentNode):

    def build_input_message(self, state: ReviewState) -> str:
        reviews = state.get("reviews") or []
        joined = "\n\n".join(f"- {review}" for review in reviews) if reviews else "(no reviews)"
        return f"Synthesize the following {len(reviews)} reviews into a meta-review:\n\n{joined}"

    def update_review_status(self, state: ReviewState, response: AgentResponse, run: AgentRun) -> dict:
        return {
            "meta_review": response.response_schema.model_dump(),
            "current_round": state["current_round"] + 1,
            "agent_runs": [run.model_dump()],
        }


class AreaChairNode(AgentNode):    
    round_offset = -1

    def build_input_message(self, state: ReviewState) -> str:
        return f"Make the final decision based on the meta-review:\n\n{state.get('meta_review')}"

    def update_review_status(self, state: ReviewState, response: AgentResponse, run: AgentRun) -> dict:
        payload = response.response_schema
        return {
            "area_chair_response": payload.model_dump(),
            "decision": payload.decision,
            "agent_runs": [run.model_dump()],
        }


class AuthorNode(AgentNode):

    round_offset = -1

    def build_input_message(self, state: ReviewState) -> str:
        reviews = state.get("reviews") or []
        return (
            f"Write a rebuttal and revisions addressing the decision "
            f"({state.get('area_chair_response')}) and {len(reviews)} reviews."
        )

    def update_review_status(self, state: ReviewState, response: AgentResponse, run: AgentRun) -> dict:
        payload = response.response_schema
        return {
            "author_response": payload.model_dump(),
            "revised_sections": {s.section_name: s.content for s in payload.revised_sections},
            "agent_runs": [run.model_dump()],
        }


class Builder:
    """Wire the review StateGraph for an arbitrary number of reviewers. ``agents``
    is keyed by agent name (``reviewer_1``..``reviewer_N`` + the singletons);
    reviewers are detected by role."""

    @staticmethod
    def build_initial_state(paper_id: str, max_rounds: int) -> ReviewState:
        return {
            "paper_id": paper_id,
            "retrieval_metadata": None,
            "reviews": [],
            "meta_review": None,
            "area_chair_response": None,
            "decision": None,
            "author_response": None,
            "revised_sections": None,
            "current_round": 0,
            "max_rounds": max_rounds,
            "agent_runs": [],
        }

    @staticmethod
    def build_graph(agents: dict[str, Agent]) -> StateGraph:
        reviewers = Builder._get_reviewers(agents)
        if not reviewers:
            raise ValueError("The graph needs at least one reviewer agent.")

        graph = StateGraph(ReviewState)
        Builder._register_nodes(graph, reviewers, agents)
        Builder._register_edges(graph, reviewers)
        Builder._register_conditional_edges(graph)
        return graph

    @staticmethod
    def _register_nodes(graph: StateGraph, reviewers: list[Agent], agents: dict[str, Agent]) -> None:
        graph.add_node(_DISPATCH, lambda state: {})
        for reviewer in reviewers:
            graph.add_node(reviewer.name, ReviewerNode(reviewer))

        graph.add_node(_META, MetaReviewerNode(agents[AgentRole.META_REVIEWER.value]))
        graph.add_node(_AREA_CHAIR, AreaChairNode(agents[AgentRole.AREA_CHAIR.value]))
        graph.add_node(_AUTHOR, AuthorNode(agents[AgentRole.AUTHOR_AGENT.value]))

    @staticmethod
    def _register_edges(graph: StateGraph, reviewers: list[Agent]) -> None:
        graph.add_edge(START, _DISPATCH)
        for reviewer in reviewers:
            graph.add_edge(_DISPATCH, reviewer.name)
            graph.add_edge(reviewer.name, _META)
        graph.add_edge(_META, _AREA_CHAIR)

    @staticmethod
    def _register_conditional_edges(graph: StateGraph) -> None:    
        area_chair_dict = {"accept": END, "revise": _AUTHOR};
        author_dict = {"loop": _DISPATCH, "end": END}

        def route_after_area_chair(state: ReviewState) -> str:
            """After the Area Chair: terminate on accept/minor_revision, else revise."""
            terminal = {ChatReviewDecision.ACCEPT, ChatReviewDecision.MINOR_REVISION}
            return "accept" if state.get("decision") in terminal else "revise"

        def route_after_author(state: ReviewState) -> str:
            """After the Author: keep looping while rounds remain, else end."""
            return "end" if state["current_round"] >= state["max_rounds"] else "loop"
        
        graph.add_conditional_edges(_AREA_CHAIR, route_after_area_chair, area_chair_dict)
        graph.add_conditional_edges(_AUTHOR, route_after_author, author_dict)
    
    @staticmethod
    def _get_reviewers(agents: dict[str, Agent]) -> list[Agent]:
        return sorted(
            (a for a in agents.values() if a.agent_role is AgentRole.REVIEWER),
            key=lambda a: a.agent_index or 0,
        )

