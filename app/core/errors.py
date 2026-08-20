# app/core/errors.py
import uuid
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse

class ServiceUnavailableError(Exception):
    def __init__(self, code="service_unavailable"):
        self.code = code

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceUnavailableError)
    async def _503(_, exc: ServiceUnavailableError):
        return JSONResponse(status_code=503, content={"error": exc.code})

    @app.exception_handler(Exception)
    async def _500(request: Request, exc: Exception):
        eid = uuid.uuid4().hex[:12]
        print(f"unhandled error id={eid}: {exc!r}")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "error_id": eid},
        )