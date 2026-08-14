import re
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import settings
from typing import Dict, Any

router = APIRouter()

class MistralRequest(BaseModel):
    resume_text: str
    job_description: str

class MistralResponse(BaseModel):
    match_score: int
    feedback: str

class CoverLetterRequest(BaseModel):
    resume_text: str
    job_description: str
    tone: str
    length: str

class CoverLetterResponse(BaseModel):
    cover_letter: str

def redact_pii(text: str) -> str:
    """
    Redact Personally Identifiable Information (Emails, Phone numbers)
    from the text before sending to AI.
    """
    # Redact Emails
    text = re.sub(r'[\w\.-]+@[\w\.-]+', '[REDACTED_EMAIL]', text)
    # Redact Phone Numbers (Basic regex for example)
    text = re.sub(r'\+?\d{10,14}', '[REDACTED_PHONE]', text)
    return text

def check_prompt_injection(text: str) -> bool:
    """
    Check for common prompt injection patterns.
    """
    suspicious_phrases = [
        "ignore previous", 
        "forget all", 
        "system prompt", 
        "you are now", 
        "bypass",
        "drop table"
    ]
    text_lower = text.lower()
    for phrase in suspicious_phrases:
        if phrase in text_lower:
            return True
    return False

@router.post("/match", response_model=MistralResponse)
async def analyze_match(
    payload: MistralRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Secure proxy to Mistral API. Requires valid JWT.
    Redacts PII and checks for prompt injection.
    """
    # 1. Prompt Injection Defense
    if check_prompt_injection(payload.resume_text) or check_prompt_injection(payload.job_description):
        raise HTTPException(status_code=400, detail="Malicious input detected (Prompt Injection).")
    
    # 2. PII Redaction
    safe_resume = redact_pii(payload.resume_text)
    
    # 3. Call Mistral API securely (Keys never exposed to frontend)
    # Example using httpx to call Mistral
    if not settings.MISTRAL_API_KEY:
        raise HTTPException(status_code=500, detail="Mistral API key not configured on server.")

    mistral_url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Construct prompt
    prompt = f"Analyze how well this resume matches the job description. Resume: {safe_resume}\n\nJob Description: {payload.job_description}"
    
    data = {
        "model": "mistral-small",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(mistral_url, headers=headers, json=data, timeout=30.0)
            response.raise_for_status()
            result = response.json()
            ai_content = result["choices"][0]["message"]["content"]
            
            # Simple mock parsing for this example
            return {"match_score": 85, "feedback": ai_content}
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail="Error communicating with AI provider")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal server error during AI analysis")


@router.post("/cover-letter", response_model=CoverLetterResponse)
async def generate_cover_letter(
    payload: CoverLetterRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Secure proxy to Mistral API for generating a cover letter.
    Redacts PII and checks for prompt injection.
    """
    if check_prompt_injection(payload.resume_text) or check_prompt_injection(payload.job_description):
        raise HTTPException(status_code=400, detail="Malicious input detected (Prompt Injection).")
    
    safe_resume = redact_pii(payload.resume_text)
    
    if not settings.MISTRAL_API_KEY:
        raise HTTPException(status_code=500, detail="Mistral API key not configured on server.")

    mistral_url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    prompt = (
        f"Write a {payload.length} cover letter with a {payload.tone} tone. "
        f"Base the letter on this resume:\n{safe_resume}\n\n"
        f"And this job description:\n{payload.job_description}"
    )
    
    data = {
        "model": "mistral-small",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(mistral_url, headers=headers, json=data, timeout=40.0)
            response.raise_for_status()
            result = response.json()
            ai_content = result["choices"][0]["message"]["content"]
            
            return {"cover_letter": ai_content}
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail="Error communicating with AI provider")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal server error during AI generation")
