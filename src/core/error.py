from __future__ import annotations

class AppError(Exception):
    """Base application error. Subclasses set `status_code`; the default is 500."""

    status_code = 500

    def __init__(self, message: str, *, detail=None):
        super().__init__(message)
        self._detail = detail

    def payload(self) -> dict:
        """JSON body for the error response."""
        return {"detail": self._detail if self._detail is not None else str(self)}


class NotFoundError(AppError):
    """A requested resource does not exist (HTTP 404)."""

    status_code = 404


class ConflictError(AppError):
    """The request conflicts with the current state (HTTP 409) — e.g. a
    duplicate, or the graph not being compiled yet."""

    status_code = 409


class ValidationError(AppError):
    """The input is invalid (HTTP 400)."""

    status_code = 400


class UpstreamError(AppError):
    """A dependency failed (LLM provider, network, ...) — a server/dependency
    fault, not the client's (HTTP 502)."""

    status_code = 502