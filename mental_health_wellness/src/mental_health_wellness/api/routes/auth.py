"""Authentication and user-creation endpoints."""

from fastapi import APIRouter, HTTPException, Request

from src.mental_health_wellness.api.models import (
    AuthResponse,
    ChatRequest,
    UserCreateRequest,
    UserCreateResponse,
    UserLoginRequest,
    validate_auth_payload,
)
from src.mental_health_wellness.db.client import get_prisma_client
from src.mental_health_wellness.security.compliance import (
    DEFAULT_PRIVACY_NOTICE_VERSION,
    DEFAULT_TERMS_VERSION,
    record_audit_event,
    update_user_privacy_metadata,
)
from src.mental_health_wellness.api.rate_limit import limiter

router = APIRouter()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


@router.post("/api/user/create", response_model=UserCreateResponse)
async def create_user(request: UserCreateRequest):
    """Create a new user (or return existing if email already registered)."""
    try:
        prisma = await get_prisma_client()
        existing = await prisma.user.find_unique(where={"email": request.email})
        if existing:
            return UserCreateResponse(user_id=existing.id, email=existing.email, name=existing.name, created=False)
        user = await prisma.user.create(data={"email": request.email, "name": request.name})
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        return UserCreateResponse(user_id=user.id, email=user.email, name=user.name, created=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/auth/signup")
 
async def auth_signup(request: UserLoginRequest, http_request: Request):
    """Sign up a new user with email and password."""
    import bcrypt
    try:
        prisma = await get_prisma_client()
        email = _normalize_email(request.email)
        validate_auth_payload(email, request.password, signup=True)

        existing = await prisma.user.find_unique(where={"email": email})
        if existing:
            if existing.passwordHash:
                raise HTTPException(status_code=400, detail="Email already registered with a password.")
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(request.password.encode("utf-8"), salt)
            updated = await prisma.user.update(
                where={"id": existing.id},
                data={"passwordHash": hashed.decode("utf-8")},
            )
            await update_user_privacy_metadata(
                prisma,
                user_id=updated.id,
                privacy_notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
                terms_version=DEFAULT_TERMS_VERSION,
            )
            await record_audit_event(
                prisma,
                event_type="AUTH_SIGNUP",
                action="auth.signup.attach_password",
                subject_user_id=updated.id,
                resource_type="user",
                resource_id=updated.id,
                purpose="account security",
                legal_basis="CONTRACT",
                request=http_request,
            )
            return AuthResponse(status="success", user_id=updated.id, email=updated.email, name=updated.name)

        name = (request.name or email.split("@")[0]).strip()[:80]
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(request.password.encode("utf-8"), salt)
        user = await prisma.user.create(
            data={"email": email, "name": name, "passwordHash": hashed.decode("utf-8")}
        )
        await update_user_privacy_metadata(
            prisma,
            user_id=user.id,
            privacy_notice_version=DEFAULT_PRIVACY_NOTICE_VERSION,
            terms_version=DEFAULT_TERMS_VERSION,
        )
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        await record_audit_event(
            prisma,
            event_type="AUTH_SIGNUP",
            action="auth.signup",
            subject_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            purpose="account creation",
            legal_basis="CONTRACT",
            request=http_request,
        )
        return AuthResponse(status="success", user_id=user.id, email=user.email, name=user.name)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH] Signup failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/auth/login")
 
async def auth_login(request: UserLoginRequest, http_request: Request):
    """Log in with email and password."""
    import bcrypt
    try:
        prisma = await get_prisma_client()
        email = _normalize_email(request.email)
        validate_auth_payload(email, request.password)

        user = await prisma.user.find_unique(where={"email": email})
        if not user or not user.passwordHash:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not bcrypt.checkpw(request.password.encode("utf-8"), user.passwordHash.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await record_audit_event(
            prisma,
            event_type="AUTH_LOGIN",
            action="auth.login",
            subject_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            purpose="account authentication",
            legal_basis="CONTRACT",
            request=http_request,
        )
        return AuthResponse(status="success", user_id=user.id, email=user.email, name=user.name)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH] Login failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/user/ensure")
async def ensure_user(request: ChatRequest):
    """Ensure user exists, creating an anonymous placeholder if needed."""
    try:
        prisma = await get_prisma_client()
        user_id = request.user_id or "anonymous"
        existing = await prisma.user.find_unique(where={"id": user_id})
        if existing:
            return {"status": "success", "user_id": existing.id, "email": existing.email, "name": existing.name, "created": False}

        email = f"{user_id}@sentimind.local"
        user = await prisma.user.create(
            data={"id": user_id, "email": email, "name": "Anonymous User" if user_id == "anonymous" else user_id}
        )
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        return {"status": "success", "user_id": user.id, "email": user.email, "name": user.name, "created": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
