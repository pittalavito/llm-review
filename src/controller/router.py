"""API composition: one router per URI scope (admin, chat, agent, paper,
retrieval, graph), each declaring its own prefix. core/app.py includes only
the aggregate ``router`` below — adding a scope means adding a
``<scope>_controller.py`` and one include here."""
from fastapi import APIRouter

from controller.admin_controller import router as admin_router
from controller.agent_controller import router as agent_router
from controller.chat_controller import router as chat_router
from controller.graph_controller import router as graph_router
from controller.paper_controller import router as paper_router
from controller.promts_controller import router as prompts_router
from controller.retrieval_controller import router as retrieval_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(chat_router)
router.include_router(agent_router)
router.include_router(paper_router)
router.include_router(retrieval_router)
router.include_router(graph_router)
router.include_router(prompts_router)

# TODO Compare APIs (/compare) — comparator_controller.py when the OpenReview
# comparator lands.
