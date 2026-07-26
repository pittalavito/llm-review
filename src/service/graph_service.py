"""Orchestrates one review-graph run: compile a set of pre-built agents into the
graph and run it from an initial state, returning the final state.

Building the agents (from a GraphConfig) and persisting the resulting run are the
caller's responsibility — this service depends on neither AgentService nor
StoreService. The context provider (RAG) is not wired here yet."""
from threading import RLock

from config import Config
from core.observability import observed, LogPrefix, log_info
from core.error import ConflictError

from domain.agent.base import Agent
from domain.graph.base import Builder
from domain.models.graph import GraphConfig


class GraphService:

    @observed(LogPrefix.GRAPH_SERVICE)
    def __init__(self, config: Config):
        self._config = config
        self._graph_config: GraphConfig | None = None
        self._graph = None
        self._lock = RLock()

    @observed(LogPrefix.GRAPH_SERVICE)
    def compile(self, agents: dict[str, Agent], graph_config: GraphConfig) -> None:
        with self._lock:
            self._graph_config = graph_config
            self._graph = Builder.build_graph(agents).compile()

    @observed(LogPrefix.GRAPH_SERVICE)
    def invoke(self, paper_path: str) -> dict:
        if self._graph is None or self._graph_config is None:
            raise ConflictError("Graph not compiled. Call compile() first.")
        state = Builder.build_initial_state(paper_path, self._graph_config.max_rounds)
        return self._graph.invoke(state)

    def get_graph_config_model_dump(self) -> dict | None:
        return self._graph_config.model_dump() if self._graph_config else None

    def get_graph_config(self) -> GraphConfig | None:
        return self._graph_config
