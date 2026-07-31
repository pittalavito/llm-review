"""Abstract graph layer, agnostic of the review domain: ``BaseGraphState``
(the state TypedDict concrete graphs extend), ``Graph`` (compile once with the
agents, then invoke with an initial state; subclasses register nodes/edges) and
``AgentNode`` (a LangGraph node bound to one agent: builds the task message
from the state, runs the agent, records the ``AgentResponseRecord`` and
returns the state delta). The concrete review pipeline lives in
``domain/graph/review.py``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from typing import TypedDict
from langgraph.graph import StateGraph

from domain.agent.base import Agent
from models.domain.agent import AgentResponse
from models.domain.run_record import AgentResponseRecord


class BaseGraphState(TypedDict):
    """Base state of a graph: concrete graphs subclass it with their fields.
    A TypedDict cannot also be an ABC — emptiness is what makes it 'abstract'."""


class Graph(ABC):

    state_schema: type[BaseGraphState] = BaseGraphState
    """The concrete state TypedDict — subclasses MUST override it, otherwise
    the StateGraph loses their fields and reducers (e.g. accumulating lists)."""

    def __init__(self):
        self.agents: dict[str, Agent] | None = None
        self.state: BaseGraphState | None = None
        self.graph = None

    def compile(self, agents: dict[str, Agent]):
        """Wire nodes/edges and compile the runnable graph. ``self.agents`` is
        set first: the register hooks are allowed to read it."""
        self.agents = agents
        graph = StateGraph(self.state_schema)
        self._register_nodes(graph, agents)
        self._register_edges(graph)
        self._register_conditional_edges(graph)

        self.graph = graph.compile()
        return self.graph

    def get_config(self) -> dict[str, Agent]:
        if self.agents is None:
            raise ValueError("Agents must be initialized before getting.")
        return self.agents

    def invoke(self, state: BaseGraphState) -> dict:
        if self.graph is None:
            raise ValueError("Graph must be compiled before invoking.")
        self.state = state
        return self.graph.invoke(state)

    @abstractmethod
    def build_initial_state(self, request) -> BaseGraphState:
        """Build the initial state for the graph from the run request."""

    @abstractmethod
    def _register_nodes(self, graph: StateGraph, agents: dict[str, Agent]) -> None:
        """Register the nodes in the graph."""

    @abstractmethod
    def _register_edges(self, graph: StateGraph) -> None:
        """Register the edges in the graph."""

    @abstractmethod
    def _register_conditional_edges(self, graph: StateGraph) -> None:
        """Register the conditional edges in the graph."""


class AgentNode(ABC):

    round_offset = 0
    """Correction for the recorded round, for roles that run after the meta
    reviewer already bumped ``current_round``."""

    def __init__(self, agent: Agent):
        self.agent = agent

    def __call__(self, state: BaseGraphState) -> dict:
        message = self.update_message(state)
        response = self.agent.run(message)
        record = AgentResponseRecord.from_response(
            response, round=state.get("current_round", 0) + self.round_offset,
        )
        return self.update_graph_state(state, response, record)

    @abstractmethod
    def update_message(self, state: BaseGraphState) -> str:
        """Build the input message for the agent from the current state."""

    @abstractmethod
    def update_graph_state(self, state: BaseGraphState, response: AgentResponse, record: AgentResponseRecord) -> dict:
        """Update the state based on the agent's response and the run record."""

