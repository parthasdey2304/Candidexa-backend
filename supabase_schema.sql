-- Enable pgcrypto extension for SHA-256 hashing
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Create Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR,
    full_name VARCHAR,
    auth_provider VARCHAR DEFAULT 'email',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for users
CREATE INDEX idx_users_email ON users(email);

-- 2. Create Resumes Table
CREATE TABLE resumes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    content TEXT NOT NULL,
    is_master BOOLEAN DEFAULT FALSE,
    ats_score INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create Jobs Table
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    company VARCHAR NOT NULL,
    description TEXT,
    url VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create Applications Table
CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    status VARCHAR DEFAULT 'Saved',
    match_score INTEGER DEFAULT 0,
    applied_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Function to automatically hash passwords with SHA-256 before insert or update
CREATE OR REPLACE FUNCTION hash_password_trigger()
RETURNS TRIGGER AS $$
BEGIN
    -- If hashed_password is being set, and it doesn't already look like a hex hash of length 64 (SHA-256)
    -- we hash it using SHA-256. 
    IF NEW.hashed_password IS NOT NULL AND (TG_OP = 'INSERT' OR NEW.hashed_password <> OLD.hashed_password) THEN
        IF length(NEW.hashed_password) <> 64 OR NEW.hashed_password !~ '^[0-9a-f]{64}$' THEN
            -- encode(digest('data', 'sha256'), 'hex')
            NEW.hashed_password := encode(digest(NEW.hashed_password, 'sha256'), 'hex');
        END IF;
    END IF;
    
    -- Also update updated_at timestamp
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to execute the hashing function
CREATE TRIGGER trigger_hash_password
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION hash_password_trigger();

-- Triggers for auto-updating timestamps on other tables
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_resumes_updated_at
BEFORE UPDATE ON resumes
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_applications_updated_at
BEFORE UPDATE ON applications
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
