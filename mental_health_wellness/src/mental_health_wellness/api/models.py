"""Pydantic request/response models for the Mental Health Wellness API."""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from src.mental_health_wellness.security.compliance import (
    DEFAULT_CONSENT_VERSION,
    DEFAULT_PRIVACY_NOTICE_VERSION,
    DEFAULT_TERMS_VERSION,
)


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    audio_data: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    emotion: Optional[str] = None
    sentiment: Optional[str] = None
    intensity: Optional[float] = None
    confidence: Optional[float] = None
    raw_emotion_label: Optional[str] = None
    primary_sub_emotion: Optional[str] = None
    secondary_sub_emotions: List[str] = []
    detected_symptoms: List[str] = []
    detected_behaviors: List[str] = []
    detected_contexts: List[str] = []
    emotion_scores: Dict[str, Any] = {}
    emotion_reasoning: Optional[str] = None
    emotion_label: Optional[str] = None
    crisis_detected: bool = False
    tools_used: List[str] = []
    node_trace: List[str] = []
    latency_trace: List[Dict[str, Any]] = []
    latency_summary: Dict[str, Any] = {}
    technique_reasoning: Optional[str] = None
    recommended_techniques_by_category: Dict[str, dict] = {}
    alternative_techniques: List[dict] = []
    timestamp: str


class PipelineRequest(BaseModel):
    user_id: Optional[str] = None
    message: str
    session_id: Optional[str] = None


class UserCreateRequest(BaseModel):
    email: str
    name: str


class UserCreateResponse(BaseModel):
    user_id: str
    email: str
    name: str
    created: bool


class UserLoginRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class AuthResponse(BaseModel):
    status: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    agent_ready: bool
    database_connected: bool
    timestamp: str


class WellnessTip(BaseModel):
    id: str
    title: str
    description: str
    category: str


class TechniqueRatingRequest(BaseModel):
    user_id: str
    technique_id: str
    rating: Optional[int] = None
    feedback: Optional[str] = None
    completed: bool = False
    session_id: Optional[str] = None


class TechniqueRatingResponse(BaseModel):
    status: str
    message: str
    technique_id: str


class SessionRenameRequest(BaseModel):
    title: str


class ConsentRequest(BaseModel):
    scopes: List[str] = ["WELLNESS_CHAT", "MOOD_ANALYTICS", "PERSONALIZATION", "CRISIS_SAFETY"]
    legal_basis: str = "CONSENT"
    policy_version: str = DEFAULT_CONSENT_VERSION
    notice_version: str = DEFAULT_PRIVACY_NOTICE_VERSION
    terms_version: str = DEFAULT_TERMS_VERSION
    locale: Optional[str] = "en-US"
    processing_region: Optional[str] = None


class ConsentWithdrawRequest(BaseModel):
    scopes: Optional[List[str]] = None
    reason: Optional[str] = None


class UserSettingsRequest(BaseModel):
    user_id: str
    settings: dict


class EmergencyContactRequest(BaseModel):
    name: str
    phone: str
    relation: Optional[str] = None
    channel: Optional[str] = "sms"


class OnboardingRequest(BaseModel):
    user_id: Optional[str] = None
    initial_mood: Optional[str] = None
    goals: List[str] = []
    notifications_enabled: bool = True
    crisis_location_consent: bool = False
    emergency_contact_consent: bool = False
    voice_analysis_consent: bool = False
    emergency_contacts: List[EmergencyContactRequest] = []


def validate_auth_payload(email: str, password: str, *, signup: bool = False) -> None:
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    if signup:
        has_upper = any(char.isupper() for char in password)
        has_digit = any(char.isdigit() for char in password)
        if len(password) < 8 or not has_upper or not has_digit:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters and include an uppercase letter and a number",
            )
