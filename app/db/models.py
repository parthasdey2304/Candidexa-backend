from __future__ import annotations
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, BigInteger, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.db.base import Base
from app.db.types import EncryptedString, EncryptedLargeString
from app.core.crypto import blind_index, decrypt_field, encrypt_field


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email_enc = Column("email_enc", EncryptedString(512), nullable=False)
    email_hmac = Column("email_hmac", String(64), nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=True)  # Nullable because Google auth users might not have a password
    full_name_enc = Column("full_name_enc", EncryptedString(255), nullable=True)
    auth_provider = Column(String, default="email")  # "email" or "google"
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    resumes = relationship("Resume", back_populates="owner", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="owner", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="owner", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    @hybrid_property
    def email(self) -> str | None:
        if self.email_enc is None:
            return None
        return decrypt_field(self.email_enc)

    @email.setter
    def email(self, value: str) -> None:
        self.email_enc = encrypt_field(value)
        self.email_hmac = blind_index(value)

    @hybrid_property
    def full_name(self) -> str | None:
        if self.full_name_enc is None:
            return None
        return decrypt_field(self.full_name_enc)

    @full_name.setter
    def full_name(self, value: str | None) -> None:
        if value is None:
            self.full_name_enc = None
        else:
            self.full_name_enc = encrypt_field(value)


class RefreshToken(Base):
    """Server-side whitelist for refresh-token JTIs (enables logout/revocation)."""
    __tablename__ = "refresh_tokens"

    jti = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class AIUsageLedger(Base):
    """Per-user token + spend accounting. Append-only."""
    __tablename__ = "ai_usage_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)         # gemini | mistral
    route = Column(String(64), nullable=False)            # tailor | jd_analyze | ...
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Integer, default=0, nullable=False)  # store as micro-USD integer
    status = Column(String(16), default="ok", nullable=False)
    request_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename_enc = Column("filename_enc", EncryptedString(255), nullable=True)
    storage_key_enc = Column("storage_key_enc", EncryptedString(512), nullable=False)
    raw_text_enc = Column("raw_text_enc", EncryptedLargeString, nullable=True)
    is_master = Column(Boolean, default=False)
    ats_score = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="resumes")
    applications = relationship("Application", back_populates="resume")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="jobs")
    applications = relationship("Application", back_populates="job")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="Saved")  # Saved, Applied, Interview, Rejected, Offer
    match_score = Column(Integer, default=0)
    applied_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")