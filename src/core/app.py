"""Application factory: builds and wires the FastAPI app in one place.
main.py exposes ``app = create_app()`` for uvicorn."""
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.logging import DefaultFormatter
from contextlib import asynccontextmanager

from config import Config, initialize_global_config
from core.container import Container
from core.spa import mount_spa
from controller.controller import router as chat_router

# src/core/app.py -> parents[2] is the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app() -> FastAPI:
    """Create and wire the FastAPI app."""

    config = initialize_global_config()
    configure_logging(config.app_log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = Container()
        yield

    app = FastAPI(lifespan=lifespan, title="llm-review")
    configure_cors(app)
    app.include_router(chat_router)
    mount_ui(app, config)  # last: the "/" mount shadows anything registered after it
    return app


def mount_ui(app: FastAPI, config: Config) -> None:
    """Serve the built frontend at "/" on the API port, when configured and built."""
    if not config.ui_dist_dir:
        return
    dist_dir = Path(config.ui_dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = _PROJECT_ROOT / dist_dir
    mount_spa(app, dist_dir)


def configure_cors(app: FastAPI) -> None:
    """Allow the Vite dev server to call the API directly (dev convenience;
    in deployed mode the UI is same-origin and this is a no-op)."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

def configure_logging(log_level: str) -> None:
    """Attach a single root StreamHandler at the given level (uvicorn formatter)."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s", use_colors=True))
    logging.root.setLevel(level)
    logging.root.handlers = [handler]