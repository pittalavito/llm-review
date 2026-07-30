"""Composition root: holds every dependency, wired once at startup and mounted
on ``app.state.container``. Controllers reach it via ``Depends(get_container)``."""
from fastapi import Request

from core.observability import observed, LogPrefix

from service.store_service import StoreService
from service.agent_service import AgentService
from service.retrieval_service import RetrievalService
from service.graph_service import ReviewGraphService

class Container:
    
    @observed(LogPrefix.CONTAINER)
    def __init__(self):
        
        self.store_service = StoreService()
        self.retrieval_service = RetrievalService(store_service=self.store_service)
        self.agent_service = AgentService(retrieval_service=self.retrieval_service)
        self.graph_service = ReviewGraphService(agent_service=self.agent_service)
        
def agent_service(request: Request) -> AgentService:
    """Dependency provider for AgentService."""
    return request.app.state.container.agent_service


def store_service(request: Request) -> StoreService:
    """Dependency provider for StoreService."""
    return request.app.state.container.store_service


def retrieval_service(request: Request) -> RetrievalService:
    """Dependency provider for RetrievalService."""
    return request.app.state.container.retrieval_service


def graph_service(request: Request) -> ReviewGraphService:
    """Dependency provider for GraphService."""
    return request.app.state.container.graph_service