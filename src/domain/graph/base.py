"""Self-contained graph layer: the review StateGraph and its collaborators —
``Messages`` (state -> human message per role), ``Nodes`` (wrap an agent into a
LangGraph node + the conditional-edge functions) and ``Builder`` (wire the graph
for an arbitrary number of reviewers) — all as static-method classes.

START -> dispatch -> (reviewer_1 .. reviewer_N in parallel) -> meta_reviewer ->
area_chair --accept--> END / --revise--> author_agent --loop--> dispatch /
--end--> END. Reviewers are detected by role, so the committee size is whatever
set of agents is passed in. No paper text yet — the context provider (RAG) will
be slotted into ``Messages`` later.
"""
from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph

from domain.agent.base import Agent
from domain.graph.state import ReviewState

from domain.models.agent import AgentResponse, AgentRole
from domain.models.chat import ChatReviewDecision
from domain.models.run_record import AgentRun


MessageBuilder = Callable[[ReviewState], str]
StateUpdater = Callable[[ReviewState, AgentResponse, AgentRun], dict]

_DISPATCH = "reviewers"
_META = "meta_reviewer"
_AREA_CHAIR = "area_chair"
_AUTHOR = "author_agent"


class Messages:
    """Build the human message for each agent from the current state. Every
    builder returns a non-empty string (the agent rejects empty messages). No
    paper text yet — the context provider (RAG) plugs in here later."""

    @staticmethod
    def reviewer(state: ReviewState) -> str:
        revised = state.get("revised_sections")
        if revised:
            sections = "\n\n".join(f"## {name}\n{content}" for name, content in revised.items())
            return f"Re-review the paper after the author's revisions:\n\n{sections}"
        return "Review the paper and produce your assessment."

    @staticmethod
    def meta(state: ReviewState) -> str:
        reviews = state.get("reviews") or []
        joined = "\n\n".join(f"- {review}" for review in reviews) if reviews else "(no reviews)"
        return f"Synthesize the following {len(reviews)} reviews into a meta-review:\n\n{joined}"

    @staticmethod
    def area_chair(state: ReviewState) -> str:
        return f"Make the final decision based on the meta-review:\n\n{state.get('meta_review')}"

    @staticmethod
    def author(state: ReviewState) -> str:
        reviews = state.get("reviews") or []
        return (
            f"Write a rebuttal and revisions addressing the decision "
            f"({state.get('area_chair_response')}) and {len(reviews)} reviews."
        )


class Nodes:
    """Wrap an agent into a LangGraph node, plus the two conditional-edge functions."""

    @staticmethod
    def reviewer(agent: Agent):
        def update(state, response, run) -> dict:
            return {"reviews": [response.response_schema.model_dump_json()], "agent_runs": [run.model_dump()]}
        return Nodes._make(agent, Messages.reviewer, update)

    @staticmethod
    def meta(agent: Agent):
        def update(state, response, run) -> dict:
            return {
                "meta_review": response.response_schema.model_dump(),
                "current_round": state["current_round"] + 1,
                "agent_runs": [run.model_dump()],
            }
        return Nodes._make(agent, Messages.meta, update)

    @staticmethod
    def area_chair(agent: Agent):
        def update(state, response, run) -> dict:
            payload = response.response_schema
            return {
                "area_chair_response": payload.model_dump(),
                "decision": payload.decision,
                "agent_runs": [run.model_dump()],
            }
        # runs after meta has already incremented current_round
        return Nodes._make(agent, Messages.area_chair, update, round_offset=-1)

    @staticmethod
    def author(agent: Agent):
        def update(state, response, run) -> dict:
            payload = response.response_schema
            return {
                "author_response": payload.model_dump(),
                "revised_sections": {s.section_name: s.content for s in payload.revised_sections},
                "agent_runs": [run.model_dump()],
            }
        return Nodes._make(agent, Messages.author, update, round_offset=-1)

    @staticmethod
    def area_chair_conditional(state: ReviewState) -> str:
        """After the Area Chair: terminate on accept/minor_revision, else revise."""
        terminal = {ChatReviewDecision.ACCEPT, ChatReviewDecision.MINOR_REVISION}
        return "accept" if state.get("decision") in terminal else "revise"

    @staticmethod
    def end_loop_conditional(state: ReviewState) -> str:
        """After the Author: keep looping while rounds remain, else end."""
        return "end" if state["current_round"] >= state["max_rounds"] else "loop"

    @staticmethod
    def _make(agent: Agent, build_message: MessageBuilder, build_update: StateUpdater, round_offset: int = 0):
        """Wrap an agent into a LangGraph node. ``build_message`` produces the
        human prompt from the state; ``build_update`` the state delta from the
        response; ``round_offset`` fixes the recorded round for agents that run
        after ``meta`` bumped ``current_round``."""
        def node(state: ReviewState) -> dict:
            message = build_message(state)
            response = agent.run(message)
            run = AgentRun(
                agent_role=response.agent_role,
                agent_index=response.agent_index,
                round=state["current_round"] + round_offset,
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
            return build_update(state, response, run)
        return node


class Builder:
    """Wire the review StateGraph for an arbitrary number of reviewers. ``agents``
    is keyed by agent name (``reviewer_1``..``reviewer_N`` + the singletons);
    reviewers are detected by role."""
 
    @staticmethod
    def build_initial_state(paper_path: str, max_rounds: int) -> ReviewState:
        return {
            "paper_path": paper_path,
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
        reviewers = sorted(
            (a for a in agents.values() if a.agent_role is AgentRole.REVIEWER),
            key=lambda a: a.agent_index or 0,
        )
        if not reviewers:
            raise ValueError("The graph needs at least one reviewer agent.")

        graph = StateGraph(ReviewState)
        Builder._register_nodes(graph, reviewers, agents)
        Builder._register_edges(graph, reviewers)
        Builder._register_conditional_edges(graph)
        return graph

    @staticmethod
    def _by_role(agents: dict[str, Agent], role: AgentRole) -> Agent:
        for agent in agents.values():
            if agent.agent_role is role:
                return agent
        raise ValueError(f"Missing agent for role {role}.")
    
    @staticmethod
    def _register_nodes(graph: StateGraph, reviewers: list[Agent], agents: dict[str, Agent]) -> None:
        graph.add_node(_DISPATCH, lambda state: {})  # passthrough fan-out point
        for reviewer in reviewers:
            graph.add_node(reviewer.name, Nodes.reviewer(reviewer))
        graph.add_node(_META, Nodes.meta(Builder._by_role(agents, AgentRole.META_REVIEWER)))
        graph.add_node(_AREA_CHAIR, Nodes.area_chair(Builder._by_role(agents, AgentRole.AREA_CHAIR)))
        graph.add_node(_AUTHOR, Nodes.author(Builder._by_role(agents, AgentRole.AUTHOR_AGENT)))

    @staticmethod
    def _register_edges(graph: StateGraph, reviewers: list[Agent]) -> None:
        graph.add_edge(START, _DISPATCH)
        for reviewer in reviewers:
            graph.add_edge(_DISPATCH, reviewer.name)
            graph.add_edge(reviewer.name, _META)
        graph.add_edge(_META, _AREA_CHAIR)

    @staticmethod
    def _register_conditional_edges(graph: StateGraph) -> None:
        graph.add_conditional_edges(_AREA_CHAIR, Nodes.area_chair_conditional, {"accept": END, "revise": _AUTHOR})
        graph.add_conditional_edges(_AUTHOR, Nodes.end_loop_conditional, {"loop": _DISPATCH, "end": END})
