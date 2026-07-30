"""Admin endpoints — everything under /admin."""
from fastapi import APIRouter

from config import get_config_with_secrets_masked

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/config")
def get_config() -> dict:
    """The whole app config, with secrets masked: password/api-key fields
    become asterisks (empty ones stay empty) and credentials embedded in
    URLs (e.g. DATABASE_URL) are scrubbed."""
    return get_config_with_secrets_masked()
