"""Shared helpers for the operational scripts in resource/scripts/."""
import os

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_project_root() -> Path:
    return PROJECT_ROOT


def load_env() -> None:
    """Load the repo-root .env into os.environ. Imported lazily so the venv
    bootstrap script (which runs before dependencies exist) can import utils."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")


def env_value(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    if value == default:
        print(f"WARNING: Environment variable {name} not set, using default: {default}")
    return value
