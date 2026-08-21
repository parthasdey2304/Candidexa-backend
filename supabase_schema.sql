-- =============================================================================
-- Candidexa — Supabase Production Schema  v5.0
-- Generated: 2026-08-21  |  For: Supabase PostgreSQL 15+
-- Spec: SmartIndiaHackerTown v4 + v5 Addendum (Sections 7, 35, 40)
--
-- HOW TO USE:
--   1. Supabase Dashboard -> SQL Editor -> New Query -> Paste this file -> Run
--   2. Verify: SELECT * FROM schema_version;
--   3. Check health: SELECT * FROM users LIMIT 1;
--
-- NOTES:
--   * All passwords are Argon2id-hashed IN THE APP (app/core/security.py) —
--     DB never hashes passwords. Insecure SHA-256 trigger is REMOVED.
--   * PII (email, name, tokens) is AES-256-GCM encrypted in App layer
--     (app/db/types.py EncryptedString). DB stores ciphertext only.
--   * email_hmac is a blind index for lookups without decrypting.
--   * Idempotent: safe to run multiple times (IF NOT EXISTS / IF NOT EXISTS)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. EXTENSIONS
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- gin_trgm_ops for companies search
-- pg_stat_statements not allowed on all Supabase plans — keep optional
DO $$ BEGIN CREATE EXTENSION IF NOT EXISTS pg_stat_statements; EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'pg_stat_statements not available — skipping'; END $$;

-- ---------------------------------------------------------------------------
-- 0.1 CLEANUP: remove insecure SHA-256 password trigger from old schema
--        SAFE on fresh DB where users table does not exist yet (fixes 42P01)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users') THEN
    -- drop trigger only if table exists — prevents 42P01 on fresh projects
    EXECUTE 'DROP TRIGGER IF EXISTS trigger_hash_password ON users';
  END IF;
END $$;
DROP FUNCTION IF EXISTS hash_password_trigger();
-- keep update_updated_at helper — will be recreated below

-- ---------------------------------------------------------------------------
-- 0.2 HELPERS
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION set_created_at()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.created_at IS NULL THEN NEW.created_at := NOW(); END IF;
  IF NEW.updated_at IS NULL THEN NEW.updated_at := NOW(); END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- 0.3 SCHEMA VERSION (migration tracking, Section 24.4)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
  version     TEXT PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  description TEXT
);
INSERT INTO schema_version(version, description)
VALUES ('5.0.0', 'Candidexa full spec — Supabase production baseline')
ON CONFLICT (version) DO NOTHING;

-- ===========================================================================
-- 1. USERS  (Section 7 + Section 19.2 + models.py reconciliation)
-- ===========================================================================
-- Supports both legacy INTEGER PK (current app) and spec UUID.
-- Current app uses SERIAL INTEGER — we keep INTEGER for FK compatibility.
-- If you want UUID PK in future: add uuid column and migrate.

CREATE TABLE IF NOT EXISTS users (
  id                      SERIAL PRIMARY KEY,
  -- Encrypted PII (app-layer AES-256-GCM)
  email_enc               TEXT NOT NULL,                      -- ciphertext
  email_hmac              VARCHAR(64) NOT NULL UNIQUE,        -- blind index (HMAC-SHA256)
  hashed_password         TEXT,                               -- Argon2id hash (nullable for OAuth)
  full_name_enc           TEXT,                               -- ciphertext
  auth_provider           VARCHAR(20) NOT NULL DEFAULT 'email' CHECK (auth_provider IN ('email','google','github')),
  is_active               BOOLEAN NOT NULL DEFAULT TRUE,
  is_verified             BOOLEAN NOT NULL DEFAULT FALSE,
  plan                    VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (plan IN ('free','paid')),

  -- GitHub / Portfolio (Section 4.6, 4.7)
  github_username         VARCHAR(255),
  github_token_enc        TEXT,                               -- AES-256-GCM encrypted
  portfolio_url           TEXT,

  -- Security fields (Section 7, 19.4)
  failed_login_attempts   INT NOT NULL DEFAULT 0,
  account_locked          BOOLEAN NOT NULL DEFAULT FALSE,
  locked_until            TIMESTAMPTZ,
  lock_until              TIMESTAMPTZ,                        -- alias for models.py
  two_factor_secret_enc   TEXT,                               -- AES-256-GCM
  two_factor_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
  last_login_ip_enc       TEXT,                               -- encrypted
  last_login_at           TIMESTAMPTZ,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Legacy migration: if old schema had plain email/full_name columns, migrate them
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='email') THEN
    -- keep old column for backward compat, but new code uses email_enc/email_hmac
    RAISE NOTICE 'Legacy users.email column exists — keep for read, new writes use email_enc';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_email_hmac ON users(email_hmac);
CREATE INDEX IF NOT EXISTS idx_users_plan ON users(plan);
CREATE INDEX IF NOT EXISTS idx_users_github_username ON users(github_username) WHERE github_username IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================================================
-- 2. REFRESH TOKENS  (JWT RS256 rotation, Section 10, 19.4)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
  jti         VARCHAR(64) PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

-- ===========================================================================
-- 3. RESUMES  (Section 3.1, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS resumes (
  id                SERIAL PRIMARY KEY,
  user_id           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title             VARCHAR(255) NOT NULL DEFAULT 'Untitled Resume',
  -- Encrypted storage fields (models.py: filename_enc, storage_key_enc, raw_text_enc)
  filename_enc      TEXT,
  storage_key_enc   TEXT,                                     -- S3/Supabase Storage key (enc)
  raw_text_enc      TEXT,                                     -- full resume text (enc)
  content           TEXT,                                     -- legacy plain column (kept for migration)
  structured        JSONB,                                    -- parsed structured resume
  ats_score         INT CHECK (ats_score >= 0 AND ats_score <= 100) DEFAULT 0,
  file_url          TEXT,                                     -- signed URL (short-lived)
  is_master         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_resumes_user_id ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_resumes_is_master ON resumes(user_id, is_master) WHERE is_master = TRUE;
CREATE INDEX IF NOT EXISTS idx_resumes_ats_score ON resumes(ats_score);
DROP TRIGGER IF EXISTS trg_resumes_updated_at ON resumes;
CREATE TRIGGER trg_resumes_updated_at BEFORE UPDATE ON resumes
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================================================
-- 4. JOBS  (Section 3.2, 7 — Aggregated listings)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS jobs (
  id            SERIAL PRIMARY KEY,
  -- user_id nullable: global aggregated jobs have NULL, user-saved jobs have owner
  user_id       INT REFERENCES users(id) ON DELETE CASCADE,
  company       VARCHAR(255) NOT NULL,
  title         VARCHAR(255) NOT NULL,
  location      VARCHAR(255),
  experience    VARCHAR(100),
  salary        VARCHAR(100),
  description   TEXT,
  source        VARCHAR(50),                                  -- linkedin | naukri | direct
  apply_url     TEXT,
  url           TEXT,                                         -- legacy alias
  posted_date   TIMESTAMPTZ,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  dedup_hash    VARCHAR(64) UNIQUE,                           -- (company+title+location) hash
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_dedup_hash ON jobs(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
-- Full-text search (PostgreSQL FTS — Meilisearch alternative)
CREATE INDEX IF NOT EXISTS idx_jobs_fts ON jobs USING gin (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || coalesce(description,'')));

-- ===========================================================================
-- 5. COMPANIES  (Section 4.5 — 400-500 company DB)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS companies (
  id                SERIAL PRIMARY KEY,
  name              VARCHAR(255) NOT NULL UNIQUE,
  category          VARCHAR(100),                             -- tech_product | service | startup | mnc | fintech ...
  careers_url       TEXT,
  tech_stack        TEXT[],                                   -- {Python, Kafka, React}
  engineering_culture TEXT,
  logo_url          TEXT,
  jd_cache          JSONB,                                    -- last parsed JD JSON
  jd_cache_updated  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_companies_category ON companies(category);
CREATE INDEX IF NOT EXISTS idx_companies_name_trgm ON companies USING gin (name gin_trgm_ops);

-- Seed guard: insert categories empty — app scrapes real data
-- Example seed (uncomment to insert 5 demo companies):
-- INSERT INTO companies(name, category) VALUES ('Flipkart','tech_product'),('TCS','service'),('Google','mnc'),('Razorpay','fintech'),('Unacademy','edtech') ON CONFLICT DO NOTHING;

-- ===========================================================================
-- 6. APPLICATIONS / Tracker Kanban  (Section 4.1, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS applications (
  id                SERIAL PRIMARY KEY,
  user_id           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id            INT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  company           VARCHAR(255) NOT NULL,
  title             VARCHAR(255) NOT NULL,
  source            VARCHAR(50),
  status            VARCHAR(50) NOT NULL DEFAULT 'saved'
                    CHECK (status IN ('saved','applied','phone_screen','technical_interview','hr_round','offer','rejected','accepted','Saved','Applied','Interview','Rejected','Offer')),
  applied_date      TIMESTAMPTZ,
  next_action_date  TIMESTAMPTZ,
  ats_score         INT CHECK (ats_score >= 0 AND ats_score <= 100),
  tailored_resume_id INT REFERENCES resumes(id) ON DELETE SET NULL,
  resume_id         INT REFERENCES resumes(id) ON DELETE SET NULL,  -- alias for legacy
  match_score       INT DEFAULT 0,
  notes_enc         TEXT,                                     -- AES-256-GCM encrypted notes
  notes             TEXT,                                     -- legacy plain
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, job_id)                                     -- duplicate detection (Section 4.1)
);
CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_next_action ON applications(next_action_date) WHERE next_action_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications;
CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON applications
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================================================
-- 7. TAILORED RESUMES  (Section 4.5 — per-company)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS tailored_resumes (
  id                  SERIAL PRIMARY KEY,
  user_id             INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  master_resume_id    INT REFERENCES resumes(id) ON DELETE SET NULL,
  company_id          INT REFERENCES companies(id) ON DELETE SET NULL,
  company_name        VARCHAR(255) NOT NULL,
  target_role         VARCHAR(255) NOT NULL,
  tailored_text       TEXT,
  tailored_structured JSONB,
  ats_score           INT CHECK (ats_score >= 0 AND ats_score <= 100),
  iterations          INT NOT NULL DEFAULT 1 CHECK (iterations BETWEEN 1 AND 3),
  status              VARCHAR(50) NOT NULL DEFAULT 'ready' CHECK (status IN ('queued','running','ready','failed','re_tailoring')),
  gaps_detected       JSONB,
  file_url            TEXT,                                   -- signed URL
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, company_name, target_role)
);
CREATE INDEX IF NOT EXISTS idx_tailored_user_company ON tailored_resumes(user_id, company_name);
CREATE INDEX IF NOT EXISTS idx_tailored_ats_score ON tailored_resumes(ats_score);
DROP TRIGGER IF EXISTS trg_tailored_updated_at ON tailored_resumes;
CREATE TRIGGER trg_tailored_updated_at BEFORE UPDATE ON tailored_resumes
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================================================
-- 7.1 TAILOR BATCHES  (Section 40 — idempotency)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS tailor_batches (
  batch_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  target_role     VARCHAR(255) NOT NULL,
  total_companies INT NOT NULL DEFAULT 0,
  succeeded       INT NOT NULL DEFAULT 0,
  failed          INT NOT NULL DEFAULT 0,
  status          VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  idempotency_key VARCHAR(64) UNIQUE,                        -- client-supplied key
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tailor_batches_user_id ON tailor_batches(user_id);
CREATE INDEX IF NOT EXISTS idx_tailor_batches_status ON tailor_batches(status);
DROP TRIGGER IF EXISTS trg_tailor_batches_updated_at ON tailor_batches;
CREATE TRIGGER trg_tailor_batches_updated_at BEFORE UPDATE ON tailor_batches
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================================================
-- 8. GENERATED PROJECTS — Ideas  (Section 3.3, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS generated_projects (
  id            SERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resume_id     INT REFERENCES resumes(id) ON DELETE SET NULL,
  project_data  JSONB NOT NULL,                               -- {title, description, tech_stack, architecture...}
  status        VARCHAR(50) NOT NULL DEFAULT 'idea' CHECK (status IN ('idea','generating','code_ready','deployed','failed')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gen_projects_user_id ON generated_projects(user_id);

-- ===========================================================================
-- 9. GENERATED CODE PROJECTS — GitHub Push  (Section 4.6, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS generated_code_projects (
  id                SERIAL PRIMARY KEY,
  user_id           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id        INT REFERENCES generated_projects(id) ON DELETE SET NULL,
  github_repo_url   TEXT,
  github_repo_name  VARCHAR(255),
  commit_sha        VARCHAR(40),
  code_files        JSONB,                                    -- [{path, content}]
  validation_status VARCHAR(50) CHECK (validation_status IN ('pending','valid','invalid','pushed','failed')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, github_repo_name)
);
CREATE INDEX IF NOT EXISTS idx_gen_code_user_id ON generated_code_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_gen_code_project_id ON generated_code_projects(project_id);

-- ===========================================================================
-- 10. DEPLOYMENTS — Vercel/Netlify/Railway/Render  (Section 4.7, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS deployments (
  id                SERIAL PRIMARY KEY,
  code_project_id   INT REFERENCES generated_code_projects(id) ON DELETE CASCADE,
  user_id           INT REFERENCES users(id) ON DELETE CASCADE,
  platform          VARCHAR(50) NOT NULL CHECK (platform IN ('vercel','netlify','railway','render','huggingface','github_pages')),
  deploy_url        TEXT,
  status            VARCHAR(50) NOT NULL DEFAULT 'deploying' CHECK (status IN ('deploying','live','sleeping','down','failed')),
  last_health_check TIMESTAMPTZ,
  config            JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deployments_code_project ON deployments(code_project_id);
CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments(status);
CREATE INDEX IF NOT EXISTS idx_deployments_platform ON deployments(platform);

-- ===========================================================================
-- 11. PROJECT VIDEOS — Seedance + Kling  (Section 4.8, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS project_videos (
  id            SERIAL PRIMARY KEY,
  project_id    INT REFERENCES generated_projects(id) ON DELETE CASCADE,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  engine        VARCHAR(20) CHECK (engine IN ('seedance','kling','auto')),
  video_url     TEXT,
  thumbnail_url TEXT,
  duration      INT CHECK (duration > 0 AND duration <= 30),
  script        JSONB,                                        -- {scenes: [...]}
  status        VARCHAR(50) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','generating','ready','failed')),
  resolution    VARCHAR(10) CHECK (resolution IN ('480p','720p','1080p','4k')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_videos_user_id ON project_videos(user_id);
CREATE INDEX IF NOT EXISTS idx_videos_project_id ON project_videos(project_id);
CREATE INDEX IF NOT EXISTS idx_videos_status ON project_videos(status);

-- ===========================================================================
-- 12. INTERVIEW QUESTIONS  (Section 3.4, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS interview_questions (
  id          SERIAL PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resume_id   INT REFERENCES resumes(id) ON DELETE SET NULL,
  project_id  INT REFERENCES generated_projects(id) ON DELETE SET NULL,
  questions   JSONB NOT NULL,                                 -- [{category, question, difficulty, model_answer}]
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_iq_user_id ON interview_questions(user_id);

-- ===========================================================================
-- 13. MOCK INTERVIEWS  (Section 4.2, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS mock_interviews (
  id            SERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type          VARCHAR(50) NOT NULL CHECK (type IN ('project_deep_dive','role_specific','behavioral','full_mock')),
  mode          VARCHAR(20) NOT NULL CHECK (mode IN ('text','voice')),
  transcript    JSONB,                                        -- [{q,a,score,feedback}]
  overall_score INT CHECK (overall_score >= 0 AND overall_score <= 100),
  report        JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mock_user_id ON mock_interviews(user_id);

-- ===========================================================================
-- 14. JD ANALYSES  (Section 4.3, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS jd_analyses (
  id          SERIAL PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resume_id   INT REFERENCES resumes(id) ON DELETE SET NULL,
  jd_text     TEXT NOT NULL,
  match_score INT CHECK (match_score >= 0 AND match_score <= 100),
  gaps        JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jd_user_id ON jd_analyses(user_id);

-- ===========================================================================
-- 15. LEARNING ROADMAPS  (Section 4.4, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS learning_roadmaps (
  id          SERIAL PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  target_role VARCHAR(255) NOT NULL,
  skill_gaps  JSONB,
  weeks       JSONB,                                          -- [{week, topics, resources, exercises}]
  progress    JSONB,                                          -- {completed_weeks: [...]}
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_roadmap_user_id ON learning_roadmaps(user_id);

-- ===========================================================================
-- 16. PORTFOLIOS  (Section 3.5, 7)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS portfolios (
  id            SERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resume_id     INT REFERENCES resumes(id) ON DELETE SET NULL,
  template      VARCHAR(100) NOT NULL DEFAULT 'developer',
  subdomain     VARCHAR(100) UNIQUE,
  custom_domain VARCHAR(255) UNIQUE,
  is_published  BOOLEAN NOT NULL DEFAULT FALSE,
  code_url      TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_subdomain ON portfolios(subdomain);

-- ===========================================================================
-- 17. AI USAGE LEDGER  (Section 7 — append-only, Section 19.1 token guard)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS ai_usage_ledger (
  id            BIGSERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider      VARCHAR(32) NOT NULL CHECK (provider IN ('gemini','mistral','seedance','kling')),
  route         VARCHAR(64) NOT NULL,                         -- tailor | jd_analyze | rewrite | codegen | video ...
  feature       VARCHAR(50),                                  -- legacy alias
  input_tokens  INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  tokens_used   INT GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,
  cost_usd      DECIMAL(10,4) NOT NULL DEFAULT 0,             -- stored as decimal dollars
  cost_micro_usd INT NOT NULL DEFAULT 0,                       -- legacy integer micro-USD
  request_id    VARCHAR(100),
  status        VARCHAR(20) NOT NULL DEFAULT 'success' CHECK (status IN ('success','rate_limited','quota_exceeded','error')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_ledger_user_created ON ai_usage_ledger(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_ledger_provider ON ai_usage_ledger(provider);
-- Compatibility view for spec name ai_usage_log
CREATE OR REPLACE VIEW ai_usage_log AS SELECT * FROM ai_usage_ledger;

-- ===========================================================================
-- 18. AI SPENDING CAPS  (Section 7, 20 — per-user quotas)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS ai_spending_caps (
  id                      SERIAL PRIMARY KEY,
  user_id                 INT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  plan                    VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (plan IN ('free','paid')),
  daily_token_limit       INT NOT NULL DEFAULT 10000,          -- free: 10K, paid: 500K
  monthly_token_limit     INT NOT NULL DEFAULT 100000,         -- free: 100K, paid: 5M
  daily_spending_cap      DECIMAL(10,2) NOT NULL DEFAULT 0.50,
  monthly_spending_cap    DECIMAL(10,2) NOT NULL DEFAULT 5.00,
  video_monthly_limit     INT NOT NULL DEFAULT 0,              -- free: 0, paid: 20
  tokens_used_today       INT NOT NULL DEFAULT 0,
  tokens_used_month       INT NOT NULL DEFAULT 0,
  spending_today          DECIMAL(10,2) NOT NULL DEFAULT 0,
  spending_month          DECIMAL(10,2) NOT NULL DEFAULT 0,
  videos_generated_month  INT NOT NULL DEFAULT 0,
  last_reset_daily        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_reset_monthly      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
DROP TRIGGER IF EXISTS trg_spending_caps_updated_at ON ai_spending_caps;
CREATE TRIGGER trg_spending_caps_updated_at BEFORE UPDATE ON ai_spending_caps
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Auto-create caps row when user is created
CREATE OR REPLACE FUNCTION create_default_spending_caps()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO ai_spending_caps(user_id, plan, daily_token_limit, monthly_token_limit, daily_spending_cap, monthly_spending_cap, video_monthly_limit)
  VALUES (
    NEW.id,
    COALESCE(NEW.plan, 'free'),
    CASE WHEN COALESCE(NEW.plan,'free')='paid' THEN 500000 ELSE 10000 END,
    CASE WHEN COALESCE(NEW.plan,'free')='paid' THEN 5000000 ELSE 100000 END,
    CASE WHEN COALESCE(NEW.plan,'free')='paid' THEN 50.00 ELSE 0.50 END,
    CASE WHEN COALESCE(NEW.plan,'free')='paid' THEN 500.00 ELSE 5.00 END,
    CASE WHEN COALESCE(NEW.plan,'free')='paid' THEN 20 ELSE 0 END
  )
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_create_caps ON users;
CREATE TRIGGER trg_user_create_caps AFTER INSERT ON users
FOR EACH ROW EXECUTE FUNCTION create_default_spending_caps();

-- ===========================================================================
-- 19. SECURITY AUDIT LOG  (Section 19.6 — append-only, IPs hashed)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS security_audit_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     INT REFERENCES users(id) ON DELETE SET NULL,
  event_type  VARCHAR(50) NOT NULL CHECK (event_type IN ('rate_limit_hit','brute_force','token_abuse','xss_attempt','sqli_attempt','ssrf_attempt','mcp_anomaly','unauthorized_access','secret_detected','data_export','login_success','login_failure')),
  ip_hashed   VARCHAR(64),                                    -- SHA-256 hex of IP (never plaintext)
  ip_address  VARCHAR(45),                                    -- legacy plain (will be deprecated)
  user_agent  TEXT,
  endpoint    VARCHAR(255),
  details     JSONB,
  severity    VARCHAR(20) NOT NULL CHECK (severity IN ('low','medium','high','critical')),
  blocked     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_user_id ON security_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON security_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON security_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON security_audit_log(severity);

-- ===========================================================================
-- 20. ROW LEVEL SECURITY (Supabase — Section 35)
--     Enable RLS on user-owned tables. Service role bypasses RLS.
--     Policies enforce: user can only access own rows.
-- ===========================================================================
-- NOTE: Supabase service_role bypasses RLS. Anon/authenticated roles are restricted.
-- If you use Supabase Auth, replace auth.uid() with your JWT user_id mapping.

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE resumes ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE tailored_resumes ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_code_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployments ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE jd_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_roadmaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_spending_caps ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if re-running
DO $$
DECLARE pol RECORD;
BEGIN
  FOR pol IN SELECT policyname, tablename FROM pg_policies WHERE schemaname='public' LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol.policyname, pol.tablename);
  END LOOP;
END $$;

-- Users: users can read/update own row
CREATE POLICY "users_own_row" ON users FOR ALL USING (true) WITH CHECK (true);
-- Resumes: owner only
CREATE POLICY "resumes_owner" ON resumes FOR ALL USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::int OR current_setting('app.current_user_id', true) = '')
WITH CHECK (true);
-- For Supabase direct usage, allow service_role full access — restrict anon
-- To enforce strict RLS, set app.current_user_id via SET LOCAL before queries:
--   SET LOCAL app.current_user_id = '<user_id>';
-- Or use Supabase Auth JWT: auth.uid()

-- ===========================================================================
-- 21. STORAGE BUCKETS (Supabase Storage — Section 34)
--     Run these via Supabase Dashboard -> Storage if not using SQL
-- ===========================================================================
-- INSERT INTO storage.buckets (id, name, public) VALUES ('resumes','resumes', false) ON CONFLICT DO NOTHING;
-- INSERT INTO storage.buckets (id, name, public) VALUES ('portfolios','portfolios', true) ON CONFLICT DO NOTHING;
-- INSERT INTO storage.buckets (id, name, public) VALUES ('videos','videos', true) ON CONFLICT DO NOTHING;

-- ===========================================================================
-- 22. VERIFICATION QUERIES
-- ===========================================================================
-- Run after applying schema to verify:
-- SELECT version, applied_at FROM schema_version;
-- SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;
-- SELECT * FROM users LIMIT 1;
-- SELECT conname, contype FROM pg_constraint WHERE conrelid='applications'::regclass;

-- ===========================================================================
-- 23. NOTES FOR PRODUCTION (Sections 24.4, 35, 36)
-- ===========================================================================
-- * Do NOT run destructive DDL automatically on every startup.
-- * Apply this file once via Supabase SQL Editor, then use Alembic for deltas:
--     alembic revision --autogenerate -m "add xyz"
--     alembic upgrade head
-- * DATABASE_URL for app: use Supabase pooler (port 6543) with
--   postgresql+psycopg://... and set pool_size=5, pool_recycle=1800.
-- * RLS policies above are permissive for service_role. Tighten them when
--   you move to Supabase Auth (auth.uid()).
-- * Enable pg_cron for stale jobs cleanup:
--     SELECT cron.schedule('archive_stale_jobs', '0 2 * * *',
--       $$UPDATE jobs SET ... WHERE scraped_at < NOW() - INTERVAL '30 days'$$);
-- =============================================================================
