from threading import RLock
from domain.graph.review import GraphReview
from core.observability import observed, LogPrefix, log_error

from domain.agent.base import Agent
from models.domain.graph import CreateGraphReviewRequest, GraphReviewConfig
from models.domain.run_record import GraphReviewRecord

from service.agent_service import AgentService
from service.store_service import StoreService

class GraphReviewService:

    @observed(LogPrefix.GRAPH_SERVICE)
    def __init__(self, agent_service: AgentService, store_service: StoreService):
        self._agent_service = agent_service
        self._store_service = store_service
        self._config: GraphReviewConfig = GraphReviewConfig.default_config()
        self._graph: GraphReview = GraphReview()
        self._lock = RLock()

    def compile(self, request: CreateGraphReviewRequest) -> GraphReviewConfig:
        """Compile the graph from the request's configuration; returns the
        configuration now loaded (echoed by the /graph/compile endpoint)."""
        with self._lock:
            agents = self._agent_service.build_agents_for_graph(request)
            self._config = request.graph_config
            self._graph.compile(agents)
            return self._config

    def get_config(self) -> GraphReviewConfig:
        """The configuration currently loaded (the default before any compile)."""
        with self._lock:
            return self._config

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