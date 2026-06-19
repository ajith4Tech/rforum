"""
Request tracing middleware + structured JSON log formatter.

Every request gets a trace_id (sourced from X-Trace-ID header or generated fresh).
The ID is stored on request.state.trace_id and echoed in the response header.
"""
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_http_logger = logging.getLogger("rforum.http")


class RequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        start = time.monotonic()

        response: Response = await call_next(request)

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id

        _http_logger.info(
            "http_request",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "ip": request.client.host if request.client else None,
            },
        )

        return response


class JSONFormatter(logging.Formatter):
    """Emit every log record as a single-line JSON object."""

    _SKIP = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        entry: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k not in self._SKIP:
                entry[k] = v
        return json.dumps(entry, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Switch the root rforum logger to structured JSON output."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger("rforum")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
