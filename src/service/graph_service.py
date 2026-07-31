from threading import RLock
from domain.graph.review import ReviewGraph
from core.observability import observed, LogPrefix, log_error

from domain.agent.base import Agent
from models.domain.graph import CreateGraphReviewRequest, ReviewGraphConfig
from models.domain.run_record import GraphReviewRecord

from service.agent_service import AgentService
from service.store_service import StoreService

class ReviewGraphService:

    @observed(LogPrefix.GRAPH_SERVICE)
    def __init__(self, agent_service: AgentService, store_service: StoreService):
        self._agent_service = agent_service
        self._store_service = store_service
        self._config: ReviewGraphConfig = ReviewGraphConfig.default_config()
        self._graph: ReviewGraph = ReviewGraph()
        self._lock = RLock()

    def compile(self, request: CreateGraphReviewRequest) -> dict[str, Agent]:
        """Compile the graph with the given request's configuration and return the agent config."""
        with self._lock:
            agents = self._agent_service.build_agents_for_graph(request)
            self._config = request.graph_config
            self._graph.compile(agents)
            return self._graph.get_config()

    def get_config(self) -> dict[str, Agent]:
        """Return the current graph configuration."""
        with self._lock:
            return self._graph.get_config()

    @observed(LogPrefix.GRAPH_SERVICE)
    def invoke(self, request: CreateGraphReviewRequest) -> GraphReviewRecord:
        try:
            with self._lock:
                state = self._graph.build_initial_state(request)
                result = self._graph.invoke(state)
                run_id = self._store_service.build_run_id(request.paper_id)
                record = GraphReviewRecord.from_result(result=result, request=request, run_id=run_id)
                self._store_service.save_run(record)
                return record
        except Exception as e:
            log_error(LogPrefix.GRAPH_SERVICE, f"Graph run failed: {e}")
            raise e