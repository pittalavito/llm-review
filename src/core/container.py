"""Composition root: holds every dependency, wired once at startup and mounted
on ``app.state.container``. Controllers reach it via ``Depends(get_container)``."""
from fastapi import Request

from core.observability import observed, LogPrefix

from service.store_service import StoreService
from service.chat_service import ChatService
from service.prompt_service import PromptService
from service.paper_service import PaperService
from service.agent_service import AgentService
from service.retrieval_service import RetrievalService
from service.graph_service import GraphReviewService

class Container:

    @observed(LogPrefix.CONTAINER)
    def __init__(self):
        self.store_service = StoreService()
        self.chat_service = ChatService()
        self.prompt_service = PromptService(store_service=self.store_service)
        self.paper_service = PaperService(store_service=self.store_service)
        self.retrieval_service = RetrievalService(store_service=self.store_service, chat_service=self.chat_service)
        self.agent_service = AgentService(chat_service=self.chat_service, prompt_service=self.prompt_service, retrieval_service=self.retrieval_service)
        self.graph_service = GraphReviewService(agent_service=self.agent_service, store_service=self.store_service)

def chat_service(request: Request) -> ChatService:
    """Dependency provider for ChatService."""
    return request.app.state.container.chat_service


def paper_service(request: Request) -> PaperService:
    """Dependency provider for PaperService."""
    return request.app.state.container.paper_service


def prompt_service(request: Request) -> PromptService:
    """Dependency provider for PromptService."""
    return request.app.state.container.prompt_service


def agent_service(request: Request) -> AgentService:
    """Dependency provider for AgentService."""
    return request.app.state.container.agent_service


def store_service(request: Request) -> StoreService:
    """Dependency provider for StoreService."""
    return request.app.state.container.store_service


def retrieval_service(request: Request) -> RetrievalService:
    """Dependency provider for RetrievalService."""
    return request.app.state.container.retrieval_service


def graph_service(request: Request) -> GraphReviewService:
    """Dependency provider for GraphService."""
    return request.app.state.container.graph_service