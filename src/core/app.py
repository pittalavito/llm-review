"""Application factory: builds and wires the FastAPI app in one place.
main.py exposes ``app = create_app()`` for uvicorn."""
import logging
from fastapi import FastAPI
from uvicorn.logging import DefaultFormatter
from contextlib import asynccontextmanager

from config import Config
from core.container import Container


def create_app() -> FastAPI:
    """Create and wire the FastAPI app."""
    
    config = Config()
    configure_logging(config.app_log_level)
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = Container(config)
        yield

    app = FastAPI(lifespan=lifespan, title="llm-review")
    return app

def configure_logging(log_level: str) -> None:
    """Attach a single root StreamHandler at the given level (uvicorn formatter)."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s", use_colors=True))
    logging.root.setLevel(level)
    logging.root.handlers = [handler]