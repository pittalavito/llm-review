import logging
from enum import StrEnum
from functools import wraps
from time import perf_counter

from core.error import AppError


_logger = logging.getLogger("observability")


class LogPrefix(StrEnum):
    """Category tag prepended to a service method's observability logs.
    Add the components you want to distinguish in the logs."""
    
    CONTAINER = "CONTAINER"
    DB_ENGINE = "DB_ENGINE"
    REDIS_CLIENT = "REDIS_CLIENT"
    
    REDIS_MALFORMED_DATA = "REDIS_MALFORMED_DATA"
    
    RAG_INDEX_REPOSITORY = "RAG_INDEX_REPOSITORY"
    PROMPT_REPOSITORY = "PROMPT_REPOSITORY"
    STORE_SERVICE = "STORE_SERVICE"


def log_info(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log an info message with the observability logger."""
    if prefix:
        _logger.info("[%s] %s", prefix, message, *args, **kwargs)
    else:
        _logger.info(message, *args, **kwargs)


def log_error(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log an error message with the observability logger."""
    if prefix:
        _logger.error("[%s] %s", prefix, message, *args, **kwargs)
    else:
        _logger.error(message, *args, **kwargs)  
        

def log_exception(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log an exception message with the observability logger."""
    if prefix:
        _logger.exception("[%s] %s", prefix, message, *args, **kwargs)
    else:
        _logger.exception(message, *args, **kwargs)


def log_warning(prefix: LogPrefix | None = None, message: str = "", *args, **kwargs):
    """Log a warning message with the observability logger."""
    if prefix:
        _logger.warning("[%s] %s", prefix, message, *args, **kwargs)
    else:
        _logger.warning(message, *args, **kwargs)


def observed(prefix: LogPrefix):
    """Log the outcome + duration of a service method, tagged with `prefix`.
    `[PREFIX] Class.method ok (N ms)` on success; expected AppErrors are logged
    at INFO without a traceback, anything else at ERROR with a traceback.
    Always re-raises."""

    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            label = f"[{prefix}] {type(self).__name__}.{method.__name__}"
            start = perf_counter()
            try:
                _logger.info("%s starting", label)
                result = method(self, *args, **kwargs)
            except AppError as exc:
                _logger.info("%s failed: %s", label, exc)
                raise
            except Exception:
                _logger.exception("%s crashed", label)
                raise
            _logger.info("%s ok (%.1f ms)", label, (perf_counter() - start) * 1000)
            return result

        return wrapper

    return decorator

