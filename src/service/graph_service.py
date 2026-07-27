"""Orchestrates one review-graph run, in the AgentService style: build the agents
(via AgentService), compile and run the graph, assemble the RunRecord and persist
it (via StoreService). Dependencies are injected.

Two external touch-points inside ``run``: ``_build_agents`` calls
``AgentService.build_agent`` and ``_save`` calls ``StoreService.save_run`` —
everything else (compile, invoke, record assembly) is internal.
"""
from datetime import datetime, timezone
from threading import RLock

from core.observability import observed, LogPrefix, log_error

from domain.agent.base import Agent
from domain.graph.base import Builder
from domain.models.graph import CreateGraphReviewRequest
from domain.models.run_record import AgentRun, GraphReviewRecord

from service.agent_service import AgentService


class GraphService:

    @observed(LogPrefix.GRAPH_SERVICE)
    def __init__(self, agent_service: AgentService):
        self.agent_service = agent_service
        self.store_service = agent_service.store_service
        self._lock = RLock()

    @observed(LogPrefix.GRAPH_SERVICE)
    def run(self, request: CreateGraphReviewRequest) -> GraphReviewRecord:
        """Build the agents, run the review graph, assemble and persist the run."""
        agents = self._build_agents(request)
        graph = self._compile(agents)
        result = graph.invoke(Builder.build_initial_state(request.paper_path, request.graph_config.max_rounds))
        record = self._build_record(result, request)
        self._save(record)
        return record

    def _build_agents(self, request: CreateGraphReviewRequest) -> dict[str, Agent]:
        """Build the agents for the graph, using AgentService."""
        return self.agent_service.build_agents_for_graph(request)
    
    def _compile(self, agents: dict[str, Agent]):
        with self._lock:
            return Builder.build_graph(agents).compile()

    def _save(self, record: GraphReviewRecord) -> None:
        try:
            self.store_service.save_run(record)
        except Exception:
            error_msg = f"Failed to save run record for paper: {record.paper_path}"
            log_error(LogPrefix.GRAPH_SERVICE, error_msg)

    def _build_record(self, result: dict, request: CreateGraphReviewRequest) -> GraphReviewRecord:
        agent_runs = [AgentRun.model_validate(run) for run in result.get("agent_runs", [])]
        return GraphReviewRecord(
            run_id=self.store_service.build_run_id(request.paper_path),
            timestamp=datetime.now(timezone.utc).isoformat(),
            paper_path=request.paper_path,
            run_description=request.run_description or None,
            decision=result.get("decision"),
            total_rounds=result.get("current_round", 0),
            reviews=result.get("reviews"),
            meta_review=result.get("meta_review"),
            area_chair_response=result.get("area_chair_response"),
            author_response=result.get("author_response"),
            retrieval_metadata=result.get("retrieval_metadata"),
            graph_config=request.graph_config.model_dump(),
            agent_runs=agent_runs,
        )