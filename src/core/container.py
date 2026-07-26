"""Composition root: holds every dependency, wired once at startup and mounted
on ``app.state.container``. Controllers reach it via ``Depends(get_container)``."""
from fastapi import Request

from config import Config
from core.observability import observed, LogPrefix

from service.store_service import StoreService
from service.agent_service import AgentService

class Container:
    
    @observed(LogPrefix.CONTAINER)
    def __init__(self, config: Config):
        self.config = config
        self.store_service = StoreService(config)
        self.agent_service = AgentService(config)


def agent_service(request: Request) -> AgentService:
    """Dependency provider for AgentService."""
    return request.app.state.container.agent_service