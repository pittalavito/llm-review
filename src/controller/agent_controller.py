"""Agent endpoints — everything under /agent."""
from fastapi import APIRouter

from domain.models.agent import AgentRole

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/roles")
def list_roles() -> list[AgentRole]:
    """List available agents."""
    return list(AgentRole)
