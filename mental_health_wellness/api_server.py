"""
FastAPI Server for Mental Health Wellness 
Predefined deterministic graph pipeline 
"""

# ── Force UTF-8 stdout/stderr on Windows so emoji print statements don't crash ──
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import os
import time
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the new agent
from src.mental_health_wellness.agent import chat_with_agent, get_agent, check_agent_health
from src.mental_health_wellness.db.client import get_prisma_client, close_prisma_client

# Import crisis routes
crisis_router = None
try:
    from src.mental_health_wellness.api.crisis_routes import router as crisis_router
    print("[SERVER] [OK] Crisis routes imported successfully")
except Exception as e:
    print(f"[SERVER] [WARN] Failed to import crisis routes: {e}")


# ============================================
# PYDANTIC MODELS
# ============================================

class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    audio_data: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    emotion: Optional[str] = None
    crisis_detected: bool = False
    tools_used: List[str] = []
    node_trace: List[str] = []
    technique_reasoning: Optional[str] = None
    recommended_techniques_by_category: Dict[str, dict] = {}
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
    rating: int  # 1-5
    feedback: Optional[str] = None
    completed: bool = False


class TechniqueRatingResponse(BaseModel):
    status: str
    message: str
    technique_id: str


class SessionRenameRequest(BaseModel):
    title: str

# ============================================
# LIFESPAN MANAGEMENT
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events"""
    print("\n" + "="*60)
    print("[SERVER] 🚀 SentiMind Mental Health API — Starting Up")
    print("="*60)

    # ── Database ──────────────────────────────────────────────────────────
    try:
        await get_prisma_client()
        print("[SERVER] ✅ Database connected (Supabase/PostgreSQL)")
    except Exception as e:
        print(f"[SERVER] ❌ Database connection failed: {e}")
        import traceback
        traceback.print_exc()

    # ── LLM Provider (OpenRouter) ─────────────────────────────────────────
    try:
        print("[SERVER] 🔄 Initializing LLM provider (OpenRouter)...")
        from src.mental_health_wellness.llm.groq_llm import get_llm_manager
        get_llm_manager()
        print("[SERVER] ✅ LLM provider ready (OpenRouter / llama-3.3-70b)")
    except Exception as e:
        print(f"[SERVER] ❌ LLM provider initialization failed: {e}")
        import traceback
        traceback.print_exc()

    # ── Agentic Pipeline ──────────────────────────────────────────────────
    try:
        get_agent()
        print("[SERVER] ✅ Deterministic Agentic Pipeline initialized")
    except Exception as e:
        print(f"[SERVER] ❌ Pipeline initialization failed: {e}")
        import traceback
        traceback.print_exc()

    # ── Voice ML Models (preload to avoid first-request delay) ────────────
    try:
        print("[SERVER] 🔄 Preloading voice ML models (wav2vec2) & verifying Deepgram API...")
        import asyncio
        from src.mental_health_wellness.voice import preload_all_voice_models
        # Run blocking model loads in a thread pool so we don't block the event loop
        loop = asyncio.get_event_loop()
        voice_status = await loop.run_in_executor(None, preload_all_voice_models)
        ready = [k for k, v in voice_status.items() if v in ("ok", "fallback")]
        failed = [k for k, v in voice_status.items() if k not in ready]
        print(f"[SERVER] ✅ Voice models ready: {ready}")
        if failed:
            print(f"[SERVER] ⚠️  Voice models unavailable: {failed}")
    except Exception as e:
        print(f"[SERVER] ⚠️  Voice model preload failed (non-fatal): {e}")

    print("="*60)
    print("[SERVER] 🎯 All systems ready — listening for requests")
    print("="*60 + "\n")

    yield

    print("\n" + "="*60)
    print("[SERVER] 🛑 Shutting down gracefully...")
    await close_prisma_client()
    print("[SERVER] ✅ Database connection closed")
    print("[SERVER] 👋 Shutdown complete")
    print("="*60)


# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="Mental Health Wellness API",
    description="AI mental health support using LangGraph ReAct Agent",
    version="3.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include crisis routes
if crisis_router is not None:
    app.include_router(crisis_router)
    print("[SERVER] [OK] Crisis routes registered")
else:
    print("[SERVER] [WARN] Crisis routes not registered")


# ============================================
# ENDPOINTS
# ============================================

@app.get("/", response_model=dict)
async def root():
    """Health check endpoint"""
    return {
        "message": "Mental Health Wellness API - Agent Version",
        "status": "healthy",
        "version": "3.0.0"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Detailed health check"""
    db_connected = False
    agent_ready = False
    
    try:
        prisma = await get_prisma_client()
        await prisma.user.count()
        db_connected = True
    except Exception as e:
        print(f"[HEALTH] DB check failed: {e}")
    
    try:
        health = check_agent_health()
        agent_ready = health.get("agent_ready", False)
    except Exception as e:
        print(f"[HEALTH] Agent check failed: {e}")
    
    return HealthResponse(
        status="healthy" if db_connected and agent_ready else "degraded",
        version="3.0.0",
        agent_ready=agent_ready,
        database_connected=db_connected,
        timestamp=datetime.now().isoformat()
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint using the deterministic graph pipeline.
    """
    try:
        result = await chat_with_agent(
            user_id=request.user_id,
            message=request.message,
            session_id=request.session_id
        )

        return ChatResponse(
            response=result.get("response", "I'm here to listen."),
            session_id=result.get("session_id"),
            emotion=result.get("emotion"),
            crisis_detected=result.get("crisis_detected", False),
            tools_used=result.get("tools_used", []),
            node_trace=result.get("node_trace", []),
            technique_reasoning=result.get("technique_reasoning"),
            recommended_techniques_by_category=result.get("recommended_techniques_by_category", {}),
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        print(f"[ERROR] Chat failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}"
        )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    True Token Streaming chat endpoint — SSE (Server-Sent Events) with LLM streaming.
    """
    from fastapi.responses import StreamingResponse
    import json

    async def event_generator():
        audio_temp_path = None
        try:
            from src.mental_health_wellness.agent.graph import chat_with_agent_streaming
            import tempfile
            import base64
            import os
            
            if request.audio_data:
                try:
                    # Strip data URI prefix if present
                    b64_str = request.audio_data
                    if "," in b64_str:
                        b64_str = b64_str.split(",")[1]
                        
                    audio_bytes = base64.b64decode(b64_str)
                    
                    # Save to temp file
                    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tf:
                        tf.write(audio_bytes)
                        audio_temp_path = tf.name
                        print(f"[STREAM] 🎤 Saved audio buffer to {audio_temp_path}")
                except Exception as e:
                    print(f"[STREAM] ❌ Failed to decode audio_data: {e}")
            
            voice_features_for_agent = None
            final_message = request.message
            if audio_temp_path:
                from src.mental_health_wellness.nodes.voice_preprocessing import preprocess_voice_input
                
                voice_state = {
                    "audio_file_path": audio_temp_path,
                    "message": request.message
                }
                
                voice_result = await preprocess_voice_input(voice_state)
                voice_processed = voice_result.get("voice_processed", False)
                voice_features = voice_result.get("voice_features", {})
                transcription = voice_result.get("transcription", "")
                # Use transcription as the final message if available, else fall back to typed text
                final_message = voice_result.get("final_message", request.message) or request.message
                
                if voice_processed and voice_features:
                    voice_features_for_agent = voice_features
                    print(f"[STREAM] 🎯 Voice features captured: {voice_features.get('emotion')} "
                          f"(conf={voice_features.get('confidence', 0):.0%}, "
                          f"distress={voice_result.get('voice_distress_index', 0):.2f})")
                    
                    # Also inject a text annotation for the LLM response generator
                    voice_confidence = voice_features.get('confidence', 0.0)
                    voice_emotion = voice_features.get('emotion', 'neutral')
                    if voice_confidence > 0.3:
                        voice_context = (
                            f"\n[Voice Analysis: The user's voice indicates they sound {voice_emotion} "
                            f"(confidence: {voice_confidence:.0%}, arousal: {voice_features.get('arousal', 0.5):.1f}, "
                            f"valence: {voice_features.get('valence', 0.5):.1f})]"
                        )
                        final_message = final_message + voice_context
                        print(f"[STREAM] 📝 Injected voice annotation into message for LLM")
                
                # Clean up temp file now — voice features are captured, no need to keep the file
                try:
                    import os
                    if audio_temp_path and os.path.exists(audio_temp_path):
                        os.remove(audio_temp_path)
                        audio_temp_path = None  # Mark as cleaned so finally-block skips it
                        print(f"[STREAM] 🧹 Cleaned up temp audio file")
                except Exception as cleanup_err:
                    print(f"[STREAM] ⚠️ Could not cleanup audio file: {cleanup_err}")
            
            # chat_with_agent_streaming now returns an async generator yielding tokens and a final metadata event
            stream = chat_with_agent_streaming(
                user_id=request.user_id,
                message=final_message,
                session_id=request.session_id,
                voice_features=voice_features_for_agent  # Pass pre-extracted features
            )

            async for chunk_data in stream:
                if chunk_data["type"] == "token":
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk_data['content']})}\n\n"
                elif chunk_data["type"] == "done":
                    # Send metadata as final event
                    metadata = chunk_data["metadata"]
                    metadata["type"] = "done"  # Ensure type is explicitly set
                    yield f"data: {json.dumps(metadata)}\n\n"
                    print(f"[STREAM] ✅ Stream complete | Metadata sent")

        except Exception as e:
            print(f"[STREAM] ❌ Stream error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': 'Something went wrong. Please try again.'})}\n\n"
        finally:
            if audio_temp_path:
                import os
                try:
                    if os.path.exists(audio_temp_path):
                        os.remove(audio_temp_path)
                except Exception as e:
                    print(f"[STREAM] ⚠️ Could not cleanup temp audio file {audio_temp_path}: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.post("/api/pipeline/complete")
async def pipeline_complete(request: PipelineRequest):
    """
    Complete pipeline endpoint (frontend compatibility).
    Uses the same agent as /chat but with frontend-expected response format.
    """
    start_time = time.time()
    
    try:
        user_id = request.user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        result = await chat_with_agent(
            user_id=user_id,
            message=request.message,
            session_id=request.session_id
        )
        
        end_time = time.time()
        total_ms = int((end_time - start_time) * 1000)
        
        return {
            "status": "success",
            "mood_analysis": {
                "sentiment": result.get("sentiment", "neutral"),
                "emotion": result.get("emotion", "neutral"),
                "intensity": result.get("intensity", 0.5),
                "confidence": result.get("confidence", 0.8)
            },
            "response": result.get("response", "I'm here to listen."),
            "crisis_detected": result.get("crisis_detected", False),
            "session_id": result.get("session_id"),
            "tools_used": result.get("tools_used", []),
            "node_trace": result.get("node_trace", []),
            "techniques": result.get("techniques", []),
            "performance": {
                "total_ms": total_ms
            }
        }
        
    except Exception as e:
        print(f"[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "status": "success",
            "mood_analysis": {
                "sentiment": "neutral",
                "emotion": "neutral",
                "intensity": 0.5,
                "confidence": 0.5
            },
            "response": "I appreciate you sharing. How are you feeling right now?",
            "crisis_detected": False,
            "tools_used": [],
            "performance": {"total_ms": 0}
        }


@app.post("/api/user/create", response_model=UserCreateResponse)
async def create_user(request: UserCreateRequest):
    """Create a new user"""
    try:
        prisma = await get_prisma_client()
        
        existing = await prisma.user.find_unique(where={"email": request.email})
        if existing:
            return UserCreateResponse(
                user_id=existing.id,
                email=existing.email,
                name=existing.name,
                created=False
            )
        
        user = await prisma.user.create(
            data={"email": request.email, "name": request.name}
        )
        
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        
        return UserCreateResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            created=True
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/signup")
async def auth_signup(request: UserLoginRequest):
    """Sign up a new user with an email and password"""
    import bcrypt
    try:
        prisma = await get_prisma_client()
        
        existing = await prisma.user.find_unique(where={"email": request.email})
        if existing:
            if existing.passwordHash:
                raise HTTPException(status_code=400, detail="Email already strictly configured with a password.")
            else:
                # Update anonymous user with real password
                salt = bcrypt.gensalt()
                hashed = bcrypt.hashpw(request.password.encode('utf-8'), salt)
                
                updated_user = await prisma.user.update(
                    where={"id": existing.id},
                    data={"passwordHash": hashed.decode('utf-8')}
                )
                
                return AuthResponse(
                    status="success",
                    user_id=updated_user.id,
                    email=updated_user.email,
                    name=updated_user.name
                )
        
        # Completely new user
        name = request.email.split('@')[0]
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(request.password.encode('utf-8'), salt)
        
        user = await prisma.user.create(
            data={
                "email": request.email, 
                "name": name,
                "passwordHash": hashed.decode('utf-8')
            }
        )
        
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        
        return AuthResponse(
            status="success",
            user_id=user.id,
            email=user.email,
            name=user.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH ERROR] Signup failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/login")
async def auth_login(request: UserLoginRequest):
    """Log in an existing user using email and password"""
    import bcrypt
    try:
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(where={"email": request.email})
        if not user or not user.passwordHash:
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        if not bcrypt.checkpw(request.password.encode('utf-8'), user.passwordHash.encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        return AuthResponse(
            status="success",
            user_id=user.id,
            email=user.email,
            name=user.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AUTH ERROR] Login failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/user/ensure")
async def ensure_user(request: ChatRequest):
    """Ensure user exists in database, creating anonymous user if needed"""
    try:
        prisma = await get_prisma_client()
        user_id = request.user_id or "anonymous"
        
        # Try to find existing user by ID
        existing_user = await prisma.user.find_unique(where={"id": user_id})
        
        if existing_user:
            return {
                "status": "success",
                "user_id": existing_user.id,
                "email": existing_user.email,
                "name": existing_user.name,
                "created": False
            }
        
        # Create new anonymous user with placeholder email
        email = f"{user_id}@sentimind.local"
        user = await prisma.user.create(
            data={
                "id": user_id,
                "email": email,
                "name": "Anonymous User" if user_id == "anonymous" else user_id
            }
        )
        
        # Create associated records
        await prisma.userpreference.create(data={"userId": user.id})
        await prisma.userstatistics.create(data={"userId": user.id})
        
        return {
            "status": "success",
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "created": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wellness/tips", response_model=List[WellnessTip])
async def get_wellness_tips():
    """Get wellness tips"""
    return [
        WellnessTip(id="1", title="Practice Gratitude", description="Note three things you're grateful for each day.", category="mindfulness"),
        WellnessTip(id="2", title="Deep Breathing", description="Try 4-7-8 breathing when stressed.", category="breathing"),
        WellnessTip(id="3", title="Stay Connected", description="Reach out to someone today.", category="social"),
        WellnessTip(id="4", title="Move Your Body", description="Even a 10-minute walk helps.", category="physical"),
        WellnessTip(id="5", title="Limit News", description="Set specific times for news/social media.", category="boundaries")
    ]


@app.get("/api/user/{user_id}/sessions")
async def get_user_sessions(user_id: str, limit: int = 10):
    """Get user's recent sessions with all their messages"""
    try:
        prisma = await get_prisma_client()
        
        # Fetch sessions with ALL their messages
        # Note: prisma-client-py uses 'order' instead of 'order_by'
        sessions = await prisma.session.find_many(
            where={"userId": user_id},
            order={"startedAt": "desc"},
            take=limit,
            include={
                "messages": {"include": {"technique": True}}
            }
        )
        
        result_sessions = []
        for s in sessions:
            # Sort messages by createdAt in application code
            sorted_messages = sorted(s.messages, key=lambda m: m.createdAt) if s.messages else []
            
            result_sessions.append({
                "id": s.id,
                "title": s.title,
                "status": str(s.status),
                "mood_summary": str(s.moodSummary) if s.moodSummary else None,
                "started_at": s.startedAt.isoformat() if s.startedAt else None,
                "ended_at": s.endedAt.isoformat() if s.endedAt else None,
                "preview": sorted_messages[0].content[:100] if sorted_messages else None,
                "message_count": len(sorted_messages),
                "messages": [
                    {
                        "id": m.id,
                        "role": str(m.role),
                        "content": m.content,
                        "emotion": str(m.emotion) if m.emotion else None,
                        "sentiment": str(m.sentiment) if m.sentiment else None,
                        "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                        "technique": ({
                            "id": m.technique.id,
                            "name": m.technique.name,
                            "brief": m.technique.brief,
                            "description": m.technique.description,
                            "steps": m.technique.steps,
                            "duration_minutes": m.technique.durationMinutes,
                            "difficulty": str(m.technique.difficulty),
                            "category": m.technique.category.name if m.technique.category else "General",
                            "why_it_works": m.technique.whyItWorks,
                            "avg_rating": m.technique.avgRating,
                            "effectiveness": m.technique.effectiveness
                        } if getattr(m, 'technique', None) else None)
                    }
                    for m in sorted_messages
                ]
            })
        
        return {
            "status": "success",
            "sessions": result_sessions
        }
        
    except Exception as e:
        print(f"[API] Error fetching user sessions: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get all messages from a specific session"""
    try:
        prisma = await get_prisma_client()
        
        messages = await prisma.message.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"},
            include={"technique": True}
        )
        
        return {
            "status": "success",
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": str(m.role),
                    "content": m.content,
                    "emotion": str(m.emotion) if m.emotion else None,
                    "sentiment": str(m.sentiment) if m.sentiment else None,
                    "createdAt": m.createdAt.isoformat() if m.createdAt else None,
                    "technique": ({
                        "id": m.technique.id,
                        "name": m.technique.name,
                        "brief": m.technique.brief,
                        "description": m.technique.description,
                        "steps": m.technique.steps,
                        "duration_minutes": m.technique.durationMinutes,
                        "difficulty": str(m.technique.difficulty),
                        "category": m.technique.category.name if m.technique and m.technique.category else "General",
                        "why_it_works": m.technique.whyItWorks,
                        "avg_rating": m.technique.avgRating,
                        "effectiveness": m.technique.effectiveness
                    } if getattr(m, 'technique', None) else None)
                }
                for m in messages
            ]
        }
        
    except Exception as e:
        print(f"[API] Error fetching session messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/session/{session_id}/rename")
async def rename_session(session_id: str, request: SessionRenameRequest):
    """Rename a chat session"""
    try:
        prisma = await get_prisma_client()
        
        # Check if session exists
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Update the title
        updated_session = await prisma.session.update(
            where={"id": session_id},
            data={"title": request.title}
        )
        
        return {
            "status": "success",
            "session_id": session_id,
            "title": updated_session.title
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SESSION] ❌ Error renaming session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a chat session and all its messages.
    Cascade-deletes: messages → session.
    """
    try:
        print(f"[SESSION-DELETE] 🗑️  Deleting session: {session_id}")
        prisma = await get_prisma_client()

        # Verify session exists
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            print(f"[SESSION-DELETE] ⚠️  Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        # Delete all messages first (FK constraint)
        deleted_msgs = await prisma.message.delete_many(where={"sessionId": session_id})
        print(f"[SESSION-DELETE] 🧹 Deleted {deleted_msgs} messages")

        # Delete the session itself
        await prisma.session.delete(where={"id": session_id})
        print(f"[SESSION-DELETE] ✅ Session {session_id} deleted successfully")

        return {
            "status": "success",
            "session_id": session_id,
            "message": "Session and all messages permanently deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[SESSION-DELETE] ❌ Error deleting session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/stats")
async def get_user_stats_legacy(user_id: str):
    """Get user statistics (legacy endpoint)"""
    try:
        prisma = await get_prisma_client()
        stats = await prisma.userstatistics.find_unique(where={"userId": user_id})
        if not stats:
            return {"message": "No statistics found"}
        return {
            "total_sessions": stats.totalSessions,
            "total_messages": stats.totalMessages,
            "current_streak": stats.currentCheckInStreak,
            "longest_streak": stats.longestCheckInStreak,
            "average_mood": stats.averageMoodRating,
            "techniques_used": stats.totalTechniquesUsed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── New comprehensive dashboard endpoint ─────────────────────────────────────

class UserSettingsRequest(BaseModel):
    user_id: str
    settings: dict

class OnboardingRequest(BaseModel):
    user_id: Optional[str] = None
    initial_mood: Optional[str] = None
    goals: List[str] = []
    notifications_enabled: bool = True


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(user_id: str):
    """
    Comprehensive dashboard stats endpoint.
    Computes mood timeline, emotion distribution, top techniques, recent sessions,
    and psychological profile from real database records.
    """
    from collections import Counter
    from datetime import timedelta

    try:
        prisma = await get_prisma_client()

        # ── Verify user exists ────────────────────────────────────────────────
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ── UserStatistics ────────────────────────────────────────────────────
        user_stats = await prisma.userstatistics.find_unique(where={"userId": user_id})
        total_sessions = user_stats.totalSessions if user_stats else 0
        streak = user_stats.currentCheckInStreak if user_stats else 0
        techniques_tried = user_stats.totalTechniquesUsed if user_stats else 0
        avg_mood_rating = user_stats.averageMoodRating if user_stats else 5.0

        # ── Sessions (last 30 days) ───────────────────────────────────────────
        thirty_days_ago = datetime.now() - timedelta(days=30)
        sessions = await prisma.session.find_many(
            where={"userId": user_id, "startedAt": {"gte": thirty_days_ago}},
            order={"startedAt": "desc"},
            include={"messages": True, "summaries": True},
        )

        # Sessions this week
        one_week_ago = datetime.now() - timedelta(days=7)
        sessions_this_week = sum(1 for s in sessions if s.startedAt and s.startedAt >= one_week_ago)

        # ── MoodLogs (last 7 days for timeline) ───────────────────────────────
        mood_logs = await prisma.moodlog.find_many(
            where={"userId": user_id, "createdAt": {"gte": one_week_ago}},
            order={"createdAt": "asc"},
        )

        # Build 7-day mood timeline (one data point per day, avg intensity)
        from collections import defaultdict
        day_mood: dict = defaultdict(list)
        day_emotion: dict = defaultdict(list)
        DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for log in mood_logs:
            if log.createdAt:
                day_name = log.createdAt.strftime("%a")
                day_mood[day_name].append(log.intensity)
                day_emotion[day_name].append(str(log.emotion).lower() if log.emotion else "neutral")

        mood_timeline = []
        for day in DAYS:
            if day in day_mood:
                avg_intensity = sum(day_mood[day]) / len(day_mood[day])
                score = round(avg_intensity * 100)
                # Most common emotion of the day
                emotion_counts = Counter(day_emotion[day])
                top_emotion = emotion_counts.most_common(1)[0][0] if emotion_counts else "neutral"
                mood_timeline.append({"date": day, "score": score, "emotion": top_emotion})
            # If no mood log for this day, omit it (don't invent data)

        # ── Emotion Distribution (all time) ───────────────────────────────────
        all_mood_logs = await prisma.moodlog.find_many(where={"userId": user_id})
        emotion_counter = Counter(
            str(ml.emotion).lower() for ml in all_mood_logs if ml.emotion
        )
        total_logs = sum(emotion_counter.values()) or 1
        emotion_distribution = [
            {
                "emotion": emotion,
                "count": count,
                "percentage": round((count / total_logs) * 100),
            }
            for emotion, count in emotion_counter.most_common(6)
        ]

        # Top emotion
        top_emotion = emotion_counter.most_common(1)[0][0] if emotion_counter else "neutral"

        # ── Mood trend (compare last 7 days to previous 7 days) ──────────────
        two_weeks_ago = datetime.now() - timedelta(days=14)
        prev_week_logs = await prisma.moodlog.find_many(
            where={"userId": user_id, "createdAt": {"gte": two_weeks_ago, "lt": one_week_ago}},
        )
        curr_avg = sum(l.intensity for l in mood_logs) / len(mood_logs) if mood_logs else 0
        prev_avg = sum(l.intensity for l in prev_week_logs) / len(prev_week_logs) if prev_week_logs else 0
        if curr_avg > prev_avg + 0.05:
            mood_trend = "up"
        elif curr_avg < prev_avg - 0.05:
            mood_trend = "down"
        else:
            mood_trend = "stable"

        # Average mood as percentage (intensity is 0-1 scale, convert to 0-100)
        avg_mood_pct = round(curr_avg * 100) if mood_logs else round((avg_mood_rating / 10) * 100)

        # ── Top Techniques ────────────────────────────────────────────────────
        technique_ratings = await prisma.usertechniquerating.find_many(
            where={"userId": user_id},
            include={"technique": {"include": {"category": True}}},
        )
        tech_counter: dict = defaultdict(lambda: {"count": 0, "name": "", "category": ""})
        for rating in technique_ratings:
            if rating.technique:
                t = rating.technique
                tid = t.id
                tech_counter[tid]["count"] += 1
                tech_counter[tid]["name"] = t.name
                tech_counter[tid]["category"] = t.category.name.lower() if t.category else "general"
        top_techniques = [
            {"name": v["name"], "category": v["category"], "usage_count": v["count"]}
            for v in sorted(tech_counter.values(), key=lambda x: x["count"], reverse=True)[:5]
        ]

        # ── Recent Sessions ───────────────────────────────────────────────────
        recent_sessions_raw = await prisma.session.find_many(
            where={"userId": user_id},
            order={"startedAt": "desc"},
            take=5,
            include={"messages": True, "summaries": True},
        )
        recent_sessions = []
        for s in recent_sessions_raw:
            # Find dominant emotion from user messages in this session
            user_emotions = [
                str(m.emotion).lower()
                for m in (s.messages or [])
                if m.role and str(m.role) == "USER" and m.emotion
            ]
            dominant = Counter(user_emotions).most_common(1)[0][0] if user_emotions else "neutral"

            # Duration from first to last message
            if s.messages:
                sorted_msgs = sorted(s.messages, key=lambda m: m.createdAt)
                if len(sorted_msgs) >= 2:
                    delta = sorted_msgs[-1].createdAt - sorted_msgs[0].createdAt
                    duration = max(1, round(delta.total_seconds() / 60))
                else:
                    duration = 1
            else:
                duration = 0

            # Technique used
            technique_name = None
            if s.summaries:
                techniques_list = s.summaries[-1].techniques if s.summaries[-1].techniques else []
                if techniques_list:
                    technique_name = techniques_list[0]

            recent_sessions.append({
                "id": s.id,
                "title": s.title or "Untitled Session",
                "date": s.startedAt.strftime("%Y-%m-%d") if s.startedAt else "",
                "dominant_emotion": dominant,
                "duration_minutes": duration,
                "technique_used": technique_name,
            })

        # ── Psychological Profile ─────────────────────────────────────────────
        psych = await prisma.psychprofile.find_unique(where={"userId": user_id})

        if psych:
            coping_raw = psych.copingStyle.lower()
            coping_map = {"avoidant": "Avoidant", "proactive": "Active", "mixed": "Mixed"}
            coping_style = coping_map.get(coping_raw, "Active")

            resilience = round(psych.resilienceScore * 100)

            anx_val = psych.anxietyBaseline
            if anx_val < 0.35:
                anxiety_baseline = "Low"
            elif anx_val < 0.65:
                anxiety_baseline = "Moderate"
            else:
                anxiety_baseline = "High"

            # Generate a short insight from available data
            if mood_trend == "up":
                ai_insight = f"Your mood has been improving this week. Your dominant coping style is {coping_style.lower()}. Keep using the techniques that work for you 💙"
            elif mood_trend == "down":
                ai_insight = f"This week has been challenging. Remember: reaching out is a form of strength. Your resilience score is {resilience}% 💙"
            else:
                ai_insight = f"You've been consistent this week. Your {coping_style.lower()} coping style is serving you well. Keep going 💙"
        else:
            # No psych profile yet — provide neutral defaults
            coping_style = "Active"
            resilience = 50
            anxiety_baseline = "Moderate"
            ai_insight = "Keep chatting with SentiMind to build your personalized psychological profile 💙"

        return {
            "total_sessions": total_sessions,
            "sessions_this_week": sessions_this_week,
            "avg_mood": avg_mood_pct,
            "streak": streak,
            "top_emotion": top_emotion,
            "mood_trend": mood_trend,
            "techniques_tried": techniques_tried,
            "mood_timeline": mood_timeline,
            "emotion_distribution": emotion_distribution,
            "top_techniques": top_techniques,
            "recent_sessions": recent_sessions,
            "psychological_profile": {
                "coping_style": coping_style,
                "resilience": resilience,
                "anxiety_baseline": anxiety_baseline,
                "ai_insight": ai_insight,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DASHBOARD] ❌ Error computing dashboard stats for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/profile")
async def get_user_profile(user_id: str):
    """Return user profile: name, email, plan, createdAt, and preferences."""
    try:
        prisma = await get_prisma_client()
        user = await prisma.user.find_unique(
            where={"id": user_id},
            include={"preference": True, "statistics": True},
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "created_at": user.createdAt.isoformat() if user.createdAt else None,
            "settings": {
                "dailyReminderEnabled": user.preference.dailyCheckInEnabled if user.preference else True,
                "weeklyEmailEnabled": user.preference.moodRemindersEnabled if user.preference else True,
                "sessionAutoSave": True,
                "anonymousMode": False,
                "shareLocationInCrisis": True,
                "theme": user.preference.theme if user.preference else "light",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/settings")
async def save_user_settings(request: UserSettingsRequest):
    """Save user preferences / settings."""
    try:
        prisma = await get_prisma_client()
        user = await prisma.user.find_unique(where={"id": request.user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        settings = request.settings
        pref = await prisma.userpreference.find_unique(where={"userId": request.user_id})
        update_data: dict = {}
        if "dailyReminderEnabled" in settings:
            update_data["dailyCheckInEnabled"] = bool(settings["dailyReminderEnabled"])
        if "weeklyEmailEnabled" in settings:
            update_data["moodRemindersEnabled"] = bool(settings["weeklyEmailEnabled"])
        if "theme" in settings:
            update_data["theme"] = str(settings["theme"])

        if update_data:
            if pref:
                await prisma.userpreference.update(
                    where={"userId": request.user_id}, data=update_data
                )
            else:
                update_data["userId"] = request.user_id
                await prisma.userpreference.create(data=update_data)

        return {"status": "success", "message": "Settings saved"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/onboarding")
async def save_onboarding(request: OnboardingRequest):
    """
    Persist onboarding selections: initial mood → MoodLog,
    goals → UserFact, notifications → UserPreference.
    """
    try:
        prisma = await get_prisma_client()
        user_id = request.user_id or "anonymous"

        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            return {"status": "skipped", "message": "User not found — onboarding data not saved"}

        MOOD_TO_EMOTION = {
            "great": "JOY",
            "good": "JOY",
            "okay": "NEUTRAL",
            "low": "SADNESS",
            "awful": "SADNESS",
        }
        MOOD_TO_INTENSITY = {
            "great": 0.9,
            "good": 0.75,
            "okay": 0.5,
            "low": 0.3,
            "awful": 0.1,
        }

        # Save initial mood as MoodLog
        if request.initial_mood:
            emotion = MOOD_TO_EMOTION.get(request.initial_mood, "NEUTRAL")
            intensity = MOOD_TO_INTENSITY.get(request.initial_mood, 0.5)
            await prisma.moodlog.create(
                data={
                    "userId": user_id,
                    "emotion": emotion,
                    "intensity": intensity,
                    "sentiment": "POSITIVE" if intensity >= 0.6 else "NEGATIVE" if intensity <= 0.35 else "NEUTRAL",
                    "context": "onboarding_initial_mood",
                    "method": "self_report",
                }
            )

        # Save goals as UserFacts
        for goal in request.goals:
            await prisma.userfact.create(
                data={
                    "userId": user_id,
                    "fact": f"User wellness goal: {goal}",
                    "category": "goal",
                }
            )

        # Update notification preference
        pref = await prisma.userpreference.find_unique(where={"userId": user_id})
        if pref:
            await prisma.userpreference.update(
                where={"userId": user_id},
                data={"dailyCheckInEnabled": request.notifications_enabled},
            )
        else:
            await prisma.userpreference.create(
                data={"userId": user_id, "dailyCheckInEnabled": request.notifications_enabled}
            )

        return {"status": "success", "message": "Onboarding data saved"}
    except Exception as e:
        print(f"[ONBOARDING] Error: {e}")
        # Non-critical — don't crash the user flow
        return {"status": "error", "message": str(e)}


@app.delete("/api/user/{user_id}")
async def delete_user_account(user_id: str):
    """Delete user account and all associated data (GDPR erasure)."""
    try:
        prisma = await get_prisma_client()
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        await prisma.user.delete(where={"id": user_id})
        return {"status": "success", "message": "Account permanently deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/techniques")
async def get_techniques(emotion: Optional[str] = None, category: Optional[str] = None):
    """Get available techniques"""
    try:
        prisma = await get_prisma_client()
        
        where_conditions = {"isActive": True}
        
        # For array filtering in Prisma, we need to use 'hasSome' instead of 'has'
        if emotion:
            emotion_upper = emotion.upper()
            # Map common emotion names to schema enums
            emotion_map = {
                "fear": "ANXIETY", 
                "anxiety": "ANXIETY",
                "sadness": "SADNESS", 
                "anger": "ANGER",
                "joy": "JOY", 
                "neutral": "NEUTRAL",
                "disgust": "ANGER",
                "surprise": "JOY"
            }
            target_emotion = emotion_map.get(emotion.lower(), emotion.upper())
            where_conditions["targetEmotions"] = {"hasSome": [target_emotion]}
        
        techniques = await prisma.technique.find_many(
            where=where_conditions,
            include={"category": True},
            order={"avgRating": "desc"}
        )
        
        return {
            "status": "success",
            "techniques": [
                {
                    "id": t.id,
                    "name": t.name,
                    "brief": t.brief,
                    "description": t.description,
                    "category": t.category.name if t.category else "General",
                    "duration_minutes": t.durationMinutes,
                    "difficulty": str(t.difficulty),
                    "steps": t.steps,
                    "why_it_works": t.whyItWorks,
                    "avg_rating": t.avgRating,
                    "total_ratings": t.totalRatings,
                    "effectiveness": t.effectiveness
                }
                for t in techniques
            ]
        }
        
    except Exception as e:
        print(f"[API] Error fetching techniques: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching techniques: {str(e)}")


@app.post("/api/technique/rate", response_model=TechniqueRatingResponse)
async def rate_technique(request: TechniqueRatingRequest):
    """Submit rating and feedback for a technique"""
    try:
        # Validate rating is between 1-5
        if not (1 <= request.rating <= 5):
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        
        prisma = await get_prisma_client()
        
        # Create the user technique rating
        rating = await prisma.usertechniquerating.create(
            data={
                "userId": request.user_id,
                "techniqueId": request.technique_id,
                "rating": request.rating,
                "feedback": request.feedback,
                "completed": request.completed
            }
        )
        
        # Update technique average rating and total ratings count
        technique = await prisma.technique.find_unique(
            where={"id": request.technique_id},
            include={"userRatings": True}
        )
        
        if technique:
            # Recalculate average rating
            all_ratings = technique.userRatings
            if all_ratings:
                avg_rating = sum(r.rating for r in all_ratings) / len(all_ratings)
                total_ratings = len(all_ratings)
                
                await prisma.technique.update(
                    where={"id": request.technique_id},
                    data={
                        "avgRating": round(avg_rating, 2),
                        "totalRatings": total_ratings
                    }
                )
        
        return {
            "status": "success",
            "message": "Thank you for your feedback!",
            "technique_id": request.technique_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error rating technique: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving rating: {str(e)}")


# ============================================
# CONSENT & GDPR ENDPOINTS
# ============================================

@app.post("/api/user/{user_id}/consent")
async def record_consent(user_id: str):
    """Record user's consent for data processing (GDPR compliance)"""
    try:
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        updated = await prisma.user.update(
            where={"id": user_id},
            data={
                "consentGiven": True,
                "consentDate": datetime.now()
            }
        )
        
        return {
            "status": "success",
            "consent_given": True,
            "consent_date": updated.consentDate.isoformat() if updated.consentDate else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/data-export")
async def export_user_data(user_id: str):
    """Export all user data (GDPR Article 15 - Right of Access)"""
    try:
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(
            where={"id": user_id},
            include={
                "sessions": {"include": {"messages": True}},
                "moodLogs": True,
                "techniqueRatings": True,
                "crisisLogs": True,
                "preference": True,
                "statistics": True
            }
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Format data for export (no internal IDs)
        export = {
            "user": {
                "name": user.name,
                "email": user.email,
                "created_at": user.createdAt.isoformat() if user.createdAt else None,
                "consent_given": user.consentGiven,
                "consent_date": user.consentDate.isoformat() if user.consentDate else None
            },
            "sessions": [
                {
                    "title": s.title,
                    "started_at": s.startedAt.isoformat() if s.startedAt else None,
                    "messages": [
                        {"role": str(m.role), "content": m.content, "emotion": str(m.emotion) if m.emotion else None}
                        for m in (s.messages or [])
                    ]
                }
                for s in (user.sessions or [])
            ],
            "mood_logs": [
                {
                    "emotion": str(ml.emotion) if ml.emotion else None,
                    "intensity": ml.intensity,
                    "logged_at": ml.loggedAt.isoformat() if ml.loggedAt else None
                }
                for ml in (user.moodLogs or [])
            ],
            "technique_ratings": [
                {"rating": tr.rating, "feedback": tr.feedback, "completed": tr.completed}
                for tr in (user.techniqueRatings or [])
            ],
            "preferences": {
                "communication_style": user.preference.communicationStyle if user.preference else None,
                "detail_level": user.preference.detailLevel if user.preference else None,
                "tone": user.preference.tone if user.preference else None
            } if user.preference else None,
            "exported_at": datetime.now().isoformat()
        }
        
        return {"status": "success", "data": export}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/user/{user_id}/data")
async def delete_user_data(user_id: str):
    """Delete all user data (GDPR Article 17 - Right to Erasure)"""
    try:
        prisma = await get_prisma_client()
        
        user = await prisma.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Cascade delete handles related records (sessions, messages, etc.)
        await prisma.user.delete(where={"id": user_id})
        
        return {
            "status": "success",
            "message": "All user data has been permanently deleted",
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# VOICE CHAT ENDPOINT
# ============================================


# ============================================
# VOICE PROCESSING HELPER
# ============================================

def try_decode_webm_to_wav(webm_bytes: bytes, output_path: str) -> bool:
    """
    Decode WebM to WAV. Since ffmpeg might not be available,
    we use librosa which can fall back to scipy or other methods.
    """
    import tempfile
    import os as _os
    
    # Save WebM to temp file
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(webm_bytes)
        tmp_webm = tmp.name
    
    success = False
    try:
        # Try with librosa first (supports many formats)
        try:
            import librosa
            import soundfile as sf
            
            print("[VOICE] 🔄 Decoding WebM with librosa...")
            y, sr = librosa.load(tmp_webm, sr=16000, mono=True)
            sf.write(output_path, y, 16000)
            print("[VOICE] ✅ WebM decoded with librosa")
            success = True
            
        except Exception as e:
            print(f"[VOICE] ⚠️ librosa failed: {e}")
            
            # Try scipy as fallback
            if not success:
                try:
                    import scipy.io.wavfile as wavfile
                    import numpy as np
                    
                    print("[VOICE] 🔄 Trying scipy.io.wavfile...")
                    sr, data = wavfile.read(tmp_webm)
                    
                    # Resample to 16kHz if needed
                    if sr != 16000:
                        ratio = 16000 / sr
                        new_length = int(len(data) * ratio)
                        data = np.interp(
                            np.linspace(0, len(data)-1, new_length),
                            np.arange(len(data)),
                            data
                        )
                    
                    wavfile.write(output_path, 16000, data.astype(np.int16))
                    print("[VOICE] ✅ WebM decoded with scipy")
                    success = True
                except Exception as scipy_err:
                    print(f"[VOICE] ⚠️ scipy failed: {scipy_err}")
                    
    finally:
        # Clean up temp file
        if _os.path.exists(tmp_webm):
            try:
                _os.unlink(tmp_webm)
            except Exception:
                pass
    
    return success


@app.post("/api/chat/voice")
async def chat_voice(
    audio: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    message: str = Form(""),
    session_id: Optional[str] = Form(None)
):
    """
    Voice-enabled chat endpoint. Routes through Voice Pre-Processing Node first.
    
    ARCHITECTURE FLOW:
    1. Convert audio blob to standardized WAV file
    2. Route to voice_preprocessing_node (Step 1: Save Audio, Step 2: Transcribe, Step 3: Extract Features)
    3. Run through main pipeline (Intake → Agent → Router → Response/Crisis → Saver)
    4. Return response with voice analysis included
    
    Audio format: WAV, MP3, WebM, or other common audio formats (16kHz+ recommended)
    """
    import tempfile
    import os as _os
    
    try:
        print(f"\n[API: VOICE] 🎤 Voice endpoint called - user: {user_id}, session: {session_id}")
        
        # ============================================
        # RECEIVE AND SAVE AUDIO
        # ============================================
        
        audio_bytes = await audio.read()
        print(f"[API: VOICE] 📥 Received {len(audio_bytes)} bytes of audio")
        
        # Detect audio format
        audio_format = _detect_audio_format(audio_bytes)
        print(f"[API: VOICE] 🔍 Detected audio format: {audio_format}")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_audio_path = tmp.name
        
        print(f"[API: VOICE] 💾 Saved audio to: {temp_audio_path}")
        
        # ============================================
        # ROUTE TO VOICE PRE-PROCESSING NODE
        # ============================================
        
        from src.mental_health_wellness.nodes.voice_preprocessing import preprocess_voice_input
        
        # Create state for voice preprocessing
        voice_state = {
            "audio_file_path": temp_audio_path,
            "message": message
        }
        
        # Run voice preprocessing
        voice_result = await preprocess_voice_input(voice_state)
        
        voice_processed = voice_result.get("voice_processed", False)
        voice_features = voice_result.get("voice_features", {})
        transcription = voice_result.get("transcription", "")
        final_message = voice_result.get("final_message", message)
        temp_audio_path = voice_result.get("temp_audio_path")  # Update in case it changed
        
        # Debug: Log what we got from voice preprocessing
        print(f"[API: VOICE] 🔍 DEBUG - voice_result keys: {list(voice_result.keys())}")
        print(f"[API: VOICE] 🔍 DEBUG - transcription from result: '{transcription}'")
        print(f"[API: VOICE] 🔍 DEBUG - final_message from result: '{final_message}'")
        print(f"[API: VOICE] 🔍 DEBUG - original message param: '{message}'")
        
        print(f"[API: VOICE] ✅ Voice preprocessing complete: voice_processed={voice_processed}")
        
        if voice_processed and voice_features:
            print(f"[API: VOICE] 🎯 Voice emotion: {voice_features.get('emotion')} "
                  f"(confidence: {voice_features.get('confidence', 0):.2f})")
        
        # ============================================
        # INJECT VOICE CONTEXT INTO MESSAGE
        # ============================================
        
        voice_confidence = voice_features.get("confidence", 0.0) if voice_features else 0.0
        voice_emotion = voice_features.get("emotion", "neutral") if voice_features else "neutral"
        
        # If voice was processed with high confidence, inject context
        if voice_processed and voice_confidence > 0.3:
            voice_context = (
                f"\n[Voice Analysis: The user's voice indicates they sound {voice_emotion} "
                f"(confidence: {voice_confidence:.0%}, arousal: {voice_features.get('arousal', 0.5):.1f}, "
                f"valence: {voice_features.get('valence', 0.5):.1f})]"
            )
            text_message_with_context = final_message + voice_context
            print(f"[API: VOICE] 🎯 Injecting voice context into message")
        else:
            text_message_with_context = final_message
        
        # ============================================
        # RUN THROUGH MAIN PIPELINE
        # ============================================
        
        print(f"[API: VOICE] ✅ Final message: '{final_message[:100]}...'")
        print(f"[API: VOICE] ✅ With context: '{text_message_with_context[:100]}...'")
        print(f"[API: VOICE] 🚀 Routing to chat_with_agent...")
        
        result = await chat_with_agent(
            user_id=user_id,
            message=text_message_with_context,
            session_id=session_id,
            audio_file_path=temp_audio_path if voice_processed else None
        )
        
        # ============================================
        # CLEANUP TEMP AUDIO FILE
        # ============================================
        
        if temp_audio_path and _os.path.exists(temp_audio_path):
            try:
                _os.unlink(temp_audio_path)
                print(f"[API: VOICE] 🧹 Cleaned up temp audio file")
            except Exception as e:
                print(f"[API: VOICE] ⚠️ Could not delete temp file: {e}")
        
        # ============================================
        # RETURN RESPONSE WITH VOICE DATA
        # ============================================
        
        return {
            "response": result.get("response", "I'm here to listen."),
            "session_id": result.get("session_id"),
            "emotion": result.get("emotion", "neutral"),
            "voice_emotion": voice_emotion if voice_processed else None,
            "voice_confidence": voice_confidence if voice_processed else 0.0,
            "transcription": transcription if voice_processed else None,
            "acoustic_features": voice_features.get("acoustic_features", {}) if voice_features else {},
            "crisis_detected": result.get("crisis_detected", False),
            "tools_used": result.get("tools_used", []),
            "has_voice": voice_processed,
            "recommended_technique": result.get("recommended_technique"),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"[API: VOICE] ❌ Voice chat failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")


def _detect_audio_format(audio_bytes: bytes) -> str:
    """
    Detect audio format from file signature (magic bytes).
    """
    if len(audio_bytes) < 4:
        return "wav"  # default
    
    if audio_bytes[:4] == b'RIFF':
        return "wav"
    elif audio_bytes[:4] == b'\xff\xfb' or audio_bytes[:2] == b'\xff\xfa':
        return "mp3"
    elif audio_bytes[4:8] == b'ftyp':
        return "mp4"
    elif audio_bytes[:4] == b'OggS':
        return "ogg"
    elif b'\x1a\x45\xdf\xa3' in audio_bytes[:100]:
        return "webm"
    else:
        return "webm"  # default


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    # Run without reload=True to avoid potential subprocess/Prisma conflicts on Windows
    # The "All connection attempts failed" error is caused by uvicorn's reloader interfering with Prisma binaries
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=False  # CHANGED: Disabled reload to fix DB connection reliability
    )