"""ASGI entry point: ``uvicorn main:app``. All wiring lives in app.create_app()."""
from core.app import create_app

app = create_app()
