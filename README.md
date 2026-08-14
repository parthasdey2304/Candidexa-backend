# Candidexa Backend API 🚀

A highly secure, high-performance FastAPI backend for the Candidexa platform. This API powers AI-driven resume matching, secure job tracking, and dynamic cover letter generation using Mistral AI.

## 🌟 Features

- **Robust Authentication**: JWT-based authentication using PyJWT, with passwords heavily hashed via SHA-256 (Passlib/Bcrypt).
- **Relational Database**: SQLAlchemy ORM with SQLite (Local Dev) ready for PostgreSQL migration.
- **AI Proxy Integration**: Secure proxy endpoints for Mistral AI, keeping API keys strictly server-side.
- **Data Protection**: 
  - Automated PII Redaction (stripping emails/phone numbers before AI processing).
  - Prompt Injection Defense checks.
- **Rate Limiting**: Integrated `slowapi` to prevent abuse and brute-force attacks.
- **Strict Security Headers**: Hardened responses against XSS, Clickjacking, and Sniffing.

## 🛠️ Tech Stack

- **Framework**: FastAPI (Python)
- **Database**: SQLAlchemy & SQLite
- **AI Integration**: Mistral AI (`mistral-small`)
- **Security**: PyJWT, Passlib, slowapi, secure

## 🚀 Getting Started (Local Development)

### 1. Prerequisites
Ensure you have Python 3.9+ installed on your machine.

### 2. Installation
Clone the repository and install the required dependencies:

```bash
git clone https://github.com/parthasdey2304/Candidexa-backend.git
cd Candidexa-backend
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root of the backend directory. **Never commit this file to version control.**

Your `.env` should look like this:
```env
# Database
DATABASE_URL=sqlite:///./candidexa.db

# JWT Security
JWT_SECRET_KEY=your_super_secret_key_here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Mistral AI
MISTRAL_API_KEY=your_mistral_api_key_here
```

### 4. Running the Server
Start the Uvicorn development server:

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.
You can view the interactive Swagger documentation at `http://localhost:8000/docs`.

## 📁 Project Structure

\`\`\`text
backend/
├── app/
│   ├── api/
│   │   ├── deps.py          # Dependency injection (Auth)
│   │   └── routes/          # API endpoint logic (resumes, jobs, ai)
│   ├── core/
│   │   ├── config.py        # Environment variables & settings
│   │   └── security.py      # Hashing and JWT utilities
│   ├── db/
│   │   ├── models.py        # SQLAlchemy database models
│   │   └── session.py       # DB engine setup
│   └── schemas/             # Pydantic validation models
├── .env.example             # Template for environment variables
├── main.py                  # FastAPI application entry point
└── requirements.txt         # Python dependencies
\`\`\`

## 🔒 Security Posture
This backend was built with security-first principles:
1. **No direct DB access** from the client.
2. **AI API Keys are strictly hidden** on the server.
3. **Data Isolation**: Every endpoint enforces `get_current_user`, guaranteeing users can only ever access their own data.
4. **Rate limiting** is applied globally and specifically to high-value endpoints like AI matching to prevent cost overruns.
