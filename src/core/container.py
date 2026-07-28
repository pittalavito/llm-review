"""Composition root: holds every dependency, wired once at startup and mounted
on ``app.state.container``. Controllers reach it via ``Depends(get_container)``."""
from fastapi import Request

from core.observability import observed, LogPrefix

from service.store_service import StoreService
from service.agent_service import AgentService
from service.retrieval_service import RetrievalService
from service.graph_service import GraphService

class Container:
    
    @observed(LogPrefix.CONTAINER)
    def __init__(self):
        
        self.store_service = StoreService()
        self.retrieval_service = RetrievalService(store_service=self.store_service)
        self.agent_service = AgentService(retrieval_service=self.retrieval_service)
        self.graph_service = GraphService(agent_service=self.agent_service)
        
def agent_service(request: Request) -> AgentService:
    """Dependency provider for AgentService."""
    return request.app.state.container.agent_service

def to_implement(request: Request):
    """Dependency provider for RetrievalService."""
    return None  # Placeholder for future implementation of RetrievalService dependency