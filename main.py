from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from secure import Secure, StrictTransportSecurity, XFrameOptions, XContentTypeOptions, ReferrerPolicy
from app.core.logging_middleware import LoggingMiddleware

from app.api.routes import auth, mistral, resumes, jobs, dashboard

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize Security Headers
secure_headers = Secure(
    sts=StrictTransportSecurity().include_subdomains().preload().max_age(31536000),
    xfo=XFrameOptions().deny(),
    xcto=XContentTypeOptions().nosniff,
    rp=ReferrerPolicy().strict_origin_when_cross_origin()
)

app = FastAPI(
    title="Candidexa Backend",
    description="Secure FastAPI backend for Candidexa",
    version="1.0.0"
)

# Add Rate Limiter Exception Handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup CORS (Strictly limit to frontend domain in production)
origins = [
    "http://localhost:3000",
    # Add production frontend URL here later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom frontend logging middleware
app.add_middleware(LoggingMiddleware)

# Middleware for Security Headers
@app.middleware("http")
async def set_secure_headers(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response

@app.get("/")
@limiter.limit("10/minute")
async def root(request: Request):
    return {"message": "Welcome to Candidexa Secure API"}

@app.get("/health")
@limiter.limit("5/minute")
async def health_check(request: Request):
    return {"status": "ok"}

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(mistral.router, prefix="/api/ai", tags=["ai"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["resumes"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
