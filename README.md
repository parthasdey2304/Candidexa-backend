# Candidexa Backend API

A production-grade, security-first FastAPI backend powering the Candidexa platform — AI-driven resume matching, secure job tracking, and dynamic cover letter generation.

**Live**: `https://candidexa-backend.onrender.com`
**Supabase**: `lpgtdyktniumthilrsnc`

---

## Security Architecture

Candidexa follows a **defense-in-depth** model. No single layer is trusted alone.

### Layer 1 — Authentication

| Mechanism | Detail |
|---|---|
| Password hashing | **Argon2id** (OWASP-recommended), memory-hard: 64 MiB, 3 iterations, 2 parallelism. Not bcrypt, not SHA-256. |
| JWT access tokens | **HS256** (or RS256 optional), 15-minute expiry, JTI claim for revocation. |
| Refresh tokens | Opaque `secrets.token_urlsafe(32)`, stored DB-side, **rotation on every use** (old token revoked — defeats token theft replay). |
| CSRF | State-changing routes require `X-CSRF-Token` header matching a session-bound token. |
| Account lockout | `locked_until` timestamp enforced — brute-force login attempts trigger temporary lock. |
| Email verification | Unverified users receive `403 email_not_verified` on all protected endpoints. |

### Layer 2 — Authorization

| Mechanism | Detail |
|---|---|
| `get_current_user` | Every protected route validates JWT → DB lookup → `is_active` + `is_verified` + lockout check. |
| `require_owner()` | Object-level guard: resource must belong to the authenticated user. User A cannot read User B's resume — returns `404 resource_not_found` (not `403`, no information leakage). |
| Refresh token rotation | `rotate_refresh_token` revokes the old token immediately — stolen refresh tokens are single-use. |

### Layer 3 — Input Validation & Sanitization

| Mechanism | Detail |
|---|---|
| Pydantic schemas | All request bodies validated through strict Pydantic v2 models. |
| File upload limits | `MAX_RESUME_SIZE_MB=10`, MIME validation via `python-magic`. |
| JSON body limits | `MAX_JSON_BODY_MB=1` — prevents payload bombs. |
| PII redaction | `redact_pii()` strips emails/phones before text reaches AI providers. |
| Prompt injection defense | `ai_guard.py` screens inputs before forwarding to Gemini/Mistral. |

### Layer 4 — Rate Limiting

| Scope | Limit | Mechanism |
|---|---|---|
| Auth endpoints (login, register) | 5 req/min per IP | Redis sliding window (Lua script, atomic) |
| General API | 60 req/min per IP | Same |
| AI endpoints | 10 req/min per user | Per-user, with daily/monthly token quotas |
| Monthly AI spend cap | $25/user | Enforced via `AIUsageLedger` |

Rate limiter **fails open** — if Redis is down, requests proceed (health/readiness checks are never blocked).

### Layer 5 — Encryption at Rest

| Field | Mechanism |
|---|---|
| PII (email, name, tokens) | **AES-256-GCM** transparent column encryption via SQLAlchemy `TypeDecorator` (`EncryptedString`). DB stores ciphertext only. |
| Email lookups | **HMAC blind index** (`email_hmac`) — search without decrypting. |
| Resume text | Encrypted via `EncryptedLargeString`. |
| Encryption keys | 32-byte base64, validated on startup. Separate keys for encryption vs. blind index. Rotate every 90 days. |

### Layer 6 — Transport & Headers

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` (2 years) |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cross-Origin-Resource-Policy` | `same-origin` |
| `Content-Security-Policy` | `default-src 'self'; frame-ancestors 'none'` (production only) |

### Layer 7 — Infrastructure Security

| Mechanism | Detail |
|---|---|
| Trusted Host Middleware | Only explicitly allowed hostnames accepted — blocks Host header injection. |
| CORS | Exact-origin allowlist — no wildcards in production (enforced by `config.py` validator). |
| Docs disabled in prod | `/docs`, `/openapi.json`, `/redoc` all return `404` when `ENVIRONMENT=production`. |
| Error IDs | Unhandled exceptions return opaque `error_id` — no stack traces leak to clients. |
| Server-side keys | `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` never reach the frontend. |

### Layer 8 — AI Guardrails

| Guard | Detail |
|---|---|
| Per-request rate limit | 10 req/min per user via Redis. |
| Daily token quota | 10,000 tokens/day per user. |
| Monthly token quota | 100,000 tokens/month per user. |
| Monthly spend cap | $25/user/month. |
| Circuit breaker | 5 consecutive failures → 60s cooldown (prevents cascading provider outages from burning budget). |
| Timeout | 45s max per AI call. |
| Usage ledger | Every AI call logged: provider, tokens, cost, status, request ID — full audit trail. |

---

## Project Structure

```
backend/
├── main.py                          # FastAPI app, middleware stack, lifespan
├── requirements.txt                 # Pinned dependencies
├── supabase_schema.sql             # Full DB schema (607 lines, 20+ tables, RLS)
├── .env                             # Local env (gitignored)
├── .env.production.example          # Production env template
│
├── app/
│   ├── api/
│   │   ├── deps.py                  # Auth dependencies (JWT, owner check, CSRF, rate limits)
│   │   └── routes/
│   │       ├── auth.py              # Register, login, refresh, Google OAuth
│   │       ├── resumes.py           # Upload, parse, list, delete resumes
│   │       ├── jobs.py              # Job CRUD, matching
│   │       └── ai.py                # AI match, cover letter, suggestions
│   │
│   ├── core/
│   │   ├── config.py                # Pydantic Settings — all env vars, validators
│   │   ├── security.py              # Argon2id hashing, JWT create/decode, constant-time eq
│   │   ├── crypto.py                # AES-256-GCM encrypt/decrypt, HMAC blind index
│   │   ├── rate_limit.py            # Redis sliding-window rate limiter (Lua, fail-open)
│   │   ├── ai_guard.py              # AI usage limits, circuit breaker, PII redaction
│   │   ├── headers.py               # Security headers middleware
│   │   ├── errors.py                # Global exception handlers (500/503)
│   │   ├── logging_middleware.py    # Request ID injection
│   │   └── __init__.py
│   │
│   ├── db/
│   │   ├── base.py                  # SQLAlchemy declarative base
│   │   ├── session.py               # Async engine + session factory
│   │   ├── models.py                # All ORM models (User, Resume, Job, AIUsageLedger...)
│   │   └── types.py                 # EncryptedString / EncryptedLargeString (AES-256-GCM)
│   │
│   ├── schemas/
│   │   ├── core.py                  # Shared Pydantic schemas
│   │   └── user.py                  # User-related schemas
│   │
│   ├── services/
│   │   └── ai_gateway.py            # Gemini/Mistral proxy with guardrails
│   │
│   └── workers/
│       └── celery_app.py            # Background tasks (Celery)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.111.0 + Uvicorn |
| Database | Supabase PostgreSQL 15 (via SQLAlchemy 2.0 async + psycopg 3) |
| ORM | SQLAlchemy 2.0 (async, mapped classes) |
| Migrations | Alembic |
| Auth | PyJWT + argon2-cffi + python-jose |
| Encryption | cryptography (AES-256-GCM) |
| AI | Gemini 2.5 Flash, Mistral Small (via httpx async) |
| Rate limiting | Redis + slowapi + custom Lua sliding window |
| Background jobs | Celery |
| Testing | pytest + pytest-asyncio |
| Linting | ruff 0.5.0 |
| Hosting | Render (backend), Vercel (frontend), Supabase (DB + auth) |

---

## Database Schema

20+ tables with full Row-Level Security (RLS). Key tables:

| Table | Purpose | Security |
|---|---|---|
| `users` | User accounts | `password_hash` (Argon2id), `email_hmac` (blind index), PII encrypted |
| `refresh_tokens` | JWT refresh token store | Single-use, revoked on rotation |
| `resumes` | Uploaded resumes | `EncryptedLargeString` for text, owner-only access |
| `jobs` | Job listings | Owner-only CRUD |
| `job_applications` | Application tracking | Owner-only |
| `ai_usage_ledger` | AI call audit trail | Per-user quotas enforced |
| `schema_version` | Schema migration tracking | Idempotent apply |

Full schema: `supabase_schema.sql` (run in Supabase SQL Editor).

---

## API Endpoints

### Public

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service health check |
| GET | `/ready` | Readiness probe |
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Rotate refresh token |
| GET | `/api/v1/auth/oauth/google` | Google OAuth redirect |
| POST | `/api/v1/auth/oauth/google` | Google OAuth callback |

### Protected (require `Authorization: Bearer <token>`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/resumes` | List user's resumes |
| POST | `/api/v1/resumes` | Upload resume (PDF/DOCX) |
| GET | `/api/v1/resumes/{id}` | Get resume (owner-only) |
| DELETE | `/api/v1/resumes/{id}` | Delete resume (owner-only) |
| GET | `/api/v1/jobs` | List user's jobs |
| POST | `/api/v1/jobs` | Create job listing |
| POST | `/api/v1/ai/match` | AI resume-job match score |
| POST | `/api/v1/ai/cover-letter` | Generate cover letter |
| POST | `/api/v1/ai/suggestions` | Get improvement suggestions |

All protected endpoints enforce: valid JWT → active user → verified email → not locked → owner check → rate limit.

---

## Getting Started

### Prerequisites

- Python 3.13+ (3.14 compatible)
- Redis (for rate limiting; optional in dev — fails open)
- Supabase project or local PostgreSQL

### 1. Clone & Install

```bash
git clone https://github.com/parthasdey2304/Candidexa-backend.git
cd Candidexa-backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.production.example` to `.env` and fill in:

```bash
cp .env.production.example .env
```

Required variables:
- `DATABASE_URL` — PostgreSQL connection string (Supabase pooler port 6543)
- `JWT_SECRET` — 32+ character secret
- `FIELD_ENCRYPTION_KEY` — 32-byte base64 (AES-256-GCM)
- `FIELD_BLIND_INDEX_KEY` — 32-byte base64 (HMAC, must differ from encryption key)

### 3. Apply Database Schema

In Supabase SQL Editor, paste and run `supabase_schema.sql`. Verify:
```sql
SELECT * FROM schema_version;
```

### 4. Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API available at `http://localhost:8000`. Swagger docs at `/docs` (disabled in production).

---

## Deployment

### Render (Production)

1. Push to `main` branch
2. Render auto-deploys from `Dockerfile` or build command
3. Set all env vars in Render Dashboard (use `.env.production.example` as template)
4. Replace `[YOUR_DB_PASSWORD]` with actual Supabase DB password
5. Health check: `GET https://candidexa-backend.onrender.com/health` → `200`

### Frontend (Vercel)

Set in Vercel Dashboard:
```
NEXT_PUBLIC_API_BASE_URL=https://candidexa-backend.onrender.com/api/v1
NEXT_PUBLIC_USE_PROXY=true
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

---

## Development

### Lint

```bash
ruff check .            # Should pass: "All checks passed!"
ruff format --check .   # Format check
```

### Test

```bash
pytest
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | Yes | `development` | `production` disables docs, enables CSP header |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | — | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | — | Supabase service role key (server-only) |
| `JWT_SECRET` | Yes | — | HS256 signing key (>= 32 chars) |
| `JWT_ALGORITHM` | No | `HS256` | `HS256` or `RS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime |
| `FIELD_ENCRYPTION_KEY` | Yes | — | 32-byte base64 AES-256-GCM key |
| `FIELD_BLIND_INDEX_KEY` | Yes | — | 32-byte base64 HMAC key |
| `FRONTEND_ORIGINS` | Yes | — | Comma-separated CORS origins |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis for rate limiting |
| `GEMINI_API_KEY` | No | — | Google Gemini API key |
| `MISTRAL_API_KEY` | No | — | Mistral AI API key |
| `GOOGLE_CLIENT_ID` | No | — | Google OAuth client ID |
| `MAX_RESUME_SIZE_MB` | No | `10` | Max upload size |
| `AI_REQUESTS_PER_MINUTE` | No | `10` | Per-user AI rate limit |
| `AI_DAILY_TOKEN_LIMIT` | No | `10000` | Per-user daily AI tokens |
| `AI_MONTHLY_SPEND_USD_LIMIT` | No | `25.0` | Per-user monthly AI spend cap |

---

## Security Checklist

- [ ] All passwords Argon2id hashed (never SHA-256, never plaintext)
- [ ] PII encrypted at rest (AES-256-GCM, DB stores ciphertext only)
- [ ] Email lookups via HMAC blind index (no decryption needed)
- [ ] JWT access tokens: 15min expiry, JTI for revocation
- [ ] Refresh tokens: single-use with rotation
- [ ] CSRF protection on state-changing routes
- [ ] Account lockout after failed attempts
- [ ] Email verification required
- [ ] Rate limiting: auth (5/min), API (60/min), AI (10/min per user)
- [ ] AI usage: daily/monthly token quotas + spend cap
- [ ] Circuit breaker on AI providers
- [ ] CORS: exact origins only, no wildcards in production
- [ ] Trusted Host middleware blocks host header injection
- [ ] Security headers: HSTS, CSP, X-Frame-Options DENY, nosniff
- [ ] Docs disabled in production
- [ ] Error responses: opaque IDs only, no stack traces
- [ ] Server-side keys never exposed to frontend
- [ ] Object-level authorization (owner check on all resources)
- [ ] File upload: size + MIME validation
- [ ] DB: RLS enabled, connection pooling (port 6543)
- [ ] Schema versioning for safe migrations

---

## License

Private — Candidexa Team
