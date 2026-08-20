from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.core.logging_middleware import LoggingMiddleware
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.headers import SecurityHeadersMiddleware, get_csp_header, get_permissions_policy
from app.core.rate_limit import init_rate_limiter, close_rate_limiter

from app.api.routes import auth, mistral, resumes, jobs, dashboard, ai

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_rate_limiter()
    yield
    # Shutdown
    await close_rate_limiter()


app = FastAPI(
    title="Candidexa Backend",
    description="Secure FastAPI backend for Candidexa",
    version=settings.VERSION,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)

# Register global exception handlers
register_exception_handlers(app)

# Add Rate Limiter Exception Handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup CORS using settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

# Add custom frontend logging middleware
app.add_middleware(LoggingMiddleware)

# Add Security Headers Middleware
app.add_middleware(
    SecurityHeadersMiddleware,
    csp=get_csp_header(),
    permissions_policy=get_permissions_policy(),
)

@app.get("/")
@limiter.limit("10/minute")
async def root(request: Request):
    return {"message": "Welcome to Candidexa Secure API"}

@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok", "service": "candidexa-backend", "version": settings.VERSION}

@app.get("/ready", include_in_schema=False)
async def readiness_check():
    # Database check will be added after DB layer is finalized
    return {"status": "ready", "database": "ok"}

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(mistral.router, prefix="/api/ai", tags=["ai"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["resumes"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai-v2"])
