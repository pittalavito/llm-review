"""Shared test setup: initialize the global Config once for the whole session so
``get_global_config()`` works everywhere (repositories, chat factory, files store
now read it instead of receiving a config)."""
import pytest

from config import initialize_global_config


@pytest.fixture(scope="session", autouse=True)
def _global_config():
    initialize_global_config()
