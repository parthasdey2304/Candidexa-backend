# app/core/logging_middleware.py
import json
import time
import uuid
import re
from starlette.middleware.base import BaseHTTPMiddleware

_REDACT_KEYS = re.compile(r"(authorization|cookie|password|secret|token|api[_-]?key|database_url|resume_text)", re.I)

def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("***" if _REDACT_KEYS.search(k) else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            resp = await call_next(request)
        except Exception:
            duration = round((time.perf_counter() - start) * 1000, 2)
            print(json.dumps({
                "level": "ERROR", "request_id": rid, "method": request.method,
                "path": request.url.path, "duration_ms": duration,
                "error": "internal_server_error",
            }))
            raise
        duration = round((time.perf_counter() - start) * 1000, 2)
        resp.headers["X-Request-Id"] = rid
        print(json.dumps({
            "level": "INFO", "request_id": rid, "method": request.method,
            "path": request.url.path, "status": resp.status_code, "duration_ms": duration,
        }))
        return resp