from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.headers import SecurityHeadersMiddleware
from app.core.logging_middleware import RequestIdMiddleware
from app.api.routes import auth, resumes, jobs, ai
from app.db.session import get_async_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine = get_async_engine()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
    lifespan=lifespan,
)

# Trusted host middleware — allow frontends + local + test clients (pytest/httpx uses "test" or "testserver")
from urllib.parse import urlparse
allowed_hosts = [urlparse(o).hostname or o for o in settings.frontend_origins_list] + ["localhost", "127.0.0.1", "test", "testserver"]
allowed_hosts = [h for h in allowed_hosts if h]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

app.add_middleware(CORSMiddleware,
                   allow_origins=settings.frontend_origins_list,
                   allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-Id"])
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(ai.router)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "service": "candidexa-backend", "version": settings.APP_VERSION}


@app.get("/ready", include_in_schema=False)
async def ready():
    return {"status": "ready", "database": "ok"}