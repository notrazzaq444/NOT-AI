"""NOT AI FastAPI backend.

Preserves the existing API routes, nested Firestore layout, Gemini orchestrator,
frontend static files, and WebSocket event format while enforcing Firebase auth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from functools import lru_cache
import tempfile
import uuid
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials, firestore
from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.ai.gemini_provider import GeminiProvider
from app.ai.groq_provider import GroqProvider
from app.ai.orchestrator import Orchestrator
from app.ai.provider_base import Message
from app.config.settings import get_settings
from app.voice.stt import SpeechToText
from app.voice.tts import generate_speech


# ---------------------------------------------------------------------------
# Logging and configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("not.backend")

settings = get_settings()

# Set NOT_CORS_ORIGINS to comma-separated exact origins in production.
# Example: https://not.example.com,https://app.example.com
_default_origins = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:8000,"
    "http://127.0.0.1:8000"
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("NOT_CORS_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app = FastAPI(
    title="NOT - AI",
    version="1.0.0",
    docs_url="/docs" if os.getenv("NOT_ENV", "development") != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Firebase Admin initialization
# ---------------------------------------------------------------------------

def initialize_firebase() -> None:
    """Initialize Firebase Admin using an explicit key or ADC on the host."""
    if firebase_admin._apps:
        return

    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not service_account_path:
        for candidate in ("firebase-adminsdk.json", "serviceAccountKey.json"):
            if Path(candidate).is_file():
                service_account_path = candidate
                break

    try:
        if service_account_path:
            firebase_admin.initialize_app(
                credentials.Certificate(service_account_path)
            )
        else:
            # Works on hosts configured with Google Application Default Credentials.
            firebase_admin.initialize_app()
        logger.info("Firebase Admin initialized")
    except Exception:
        logger.exception("Firebase Admin initialization failed")


initialize_firebase()

try:
    db = firestore.client() if firebase_admin._apps else None
except Exception:
    logger.exception("Could not create Firestore client")
    db = None


# ---------------------------------------------------------------------------
# Frontend static files
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

if FRONTEND_DIR.is_dir():
    for folder in ("css", "js", "assets"):
        folder_path = FRONTEND_DIR / folder
        if folder_path.is_dir():
            app.mount(
                f"/{folder}",
                StaticFiles(directory=str(folder_path)),
                name=folder,
            )

# Whisper can be memory-heavy. Configure model size with NOT_STT_MODEL.
STT_MODEL = os.getenv("NOT_STT_MODEL", "tiny")
stt_engine: SpeechToText | None = None

try:
    stt_engine = SpeechToText(model_size=STT_MODEL)
    logger.info("Speech-to-text initialized with model '%s'", STT_MODEL)
except Exception:
    logger.exception("Speech-to-text initialization failed; /api/transcribe unavailable")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class UserSettingsRequest(BaseModel):
    language: str = Field(min_length=1, max_length=40)
    country: str = Field(min_length=2, max_length=3)


class PersonalityRequest(BaseModel):
    personality: str = Field(min_length=1, max_length=300)


class VoiceRequest(BaseModel):
    voice: str = Field(min_length=1, max_length=100)


class SyncUserRequest(BaseModel):
    # These are optional display hints only. Verified token claims take priority.
    email: str | None = None
    name: str | None = None


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def verify_firebase_token(token: str) -> dict[str, Any]:
    if not firebase_admin._apps:
        raise HTTPException(
            status_code=503,
            detail="Firebase authentication is not configured on this server",
        )

    try:
        return auth.verify_id_token(token, check_revoked=True)
    except Exception:
        logger.warning("Firebase ID token verification failed", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token")


async def get_current_user_token(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty Bearer token")

    return verify_firebase_token(token)


def _uid_from_claims(claims: dict[str, Any]) -> str:
    uid = claims.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Firebase token has no user ID")
    return str(uid)


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

DEFAULT_USER_SETTINGS = {
    "language": "en",
    "country": "PK",
    "personality": "Calm, direct and thoughtful",
    "voice": "Nova",
}


def _ensure_user_firestore(uid: str, email: str = "", name: str = "User") -> None:
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore is not available")

    user_ref = db.collection("users").document(uid)
    snapshot = user_ref.get()

    if not snapshot.exists:
        user_ref.set(
            {
                "id": uid,
                "email": email,
                "name": name,
                **DEFAULT_USER_SETTINGS,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
        )
    else:
        updates: dict[str, Any] = {}
        if email:
            updates["email"] = email
        if name and name != "User":
            updates["name"] = name
        if updates:
            user_ref.set(updates, merge=True)


def _save_message(uid: str, session_id: str, role: str, content: str) -> None:
    if db is None or not content.strip():
        return

    chat_ref = (
        db.collection("users")
        .document(uid)
        .collection("chats")
        .document(session_id)
    )

    chat_snapshot = chat_ref.get()
    title_text = (content[:28] + "…") if len(content) > 28 else content

    if not chat_snapshot.exists:
        chat_ref.set(
            {
                "id": session_id,
                "title": title_text,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
        )
    elif role == "user":
        chat_ref.update({"title": title_text})

    chat_ref.collection("messages").add(
        {
            "role": role,
            "content": content,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )


def _load_history_nested(
    uid: str,
    session_id: str,
    limit: int = 6,
) -> list[Message]:
    if db is None:
        return []

    query = (
        db.collection("users")
        .document(uid)
        .collection("chats")
        .document(session_id)
        .collection("messages")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )

    # Query newest first for efficiency, then restore chronological order.
    docs = list(query.stream())
    docs.reverse()

    messages: list[Message] = []
    for doc in docs:
        data = doc.to_dict() or {}
        role = data.get("role")
        content = data.get("content")
        if role in ("user", "assistant", "system") and isinstance(content, str):
            messages.append(Message(role=role, content=content))
    return messages


def _get_user_ref(uid: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore is not available")
    return db.collection("users").document(uid)


# ---------------------------------------------------------------------------
# Health and Firebase client configuration
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "firebase_admin": bool(firebase_admin._apps),
        "firestore": db is not None,
        "stt": stt_engine is not None,
    }


@app.get("/api/firebase-config")
def get_firebase_config():
    # Firebase web config is a client identifier, not a server secret.
    return {
        "apiKey": settings.firebase_api_key,
        "authDomain": settings.firebase_auth_domain,
        "projectId": settings.firebase_project_id,
        "storageBucket": settings.firebase_storage_bucket,
        "messagingSenderId": settings.firebase_messaging_sender_id,
        "appId": settings.firebase_app_id,
    }


# ---------------------------------------------------------------------------
# Authentication/user routes
# ---------------------------------------------------------------------------

@app.post("/api/auth/sync")
def sync_user(
    req: SyncUserRequest | None = None,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    uid = _uid_from_claims(decoded_token)

    # Never trust client-supplied email/name over verified Firebase claims.
    email = str(decoded_token.get("email") or (req.email if req else "") or "")
    name = str(decoded_token.get("name") or (req.name if req else "") or "User")

    _ensure_user_firestore(uid, email, name)
    return {"user_id": uid, "email": email, "name": name}


@app.get("/api/auth/me")
def get_me(decoded_token: dict[str, Any] = Depends(get_current_user_token)):
    uid = _uid_from_claims(decoded_token)
    user_ref = _get_user_ref(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        return user_doc.to_dict()

    return {
        "id": uid,
        "email": decoded_token.get("email", ""),
        "name": decoded_token.get("name", "User"),
    }


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------

@app.get("/api/user/settings")
def get_user_settings(decoded_token: dict[str, Any] = Depends(get_current_user_token)):
    uid = _uid_from_claims(decoded_token)
    _ensure_user_firestore(
        uid,
        str(decoded_token.get("email") or ""),
        str(decoded_token.get("name") or "User"),
    )

    data = _get_user_ref(uid).get().to_dict() or {}
    return {
        "language": data.get("language", "en"),
        "country": data.get("country", "PK"),
        "name": data.get("name", decoded_token.get("name", "User")),
        "email": data.get("email", decoded_token.get("email", "")),
        "personality": data.get(
            "personality", DEFAULT_USER_SETTINGS["personality"]
        ),
        "voice": data.get("voice", DEFAULT_USER_SETTINGS["voice"]),
    }


@app.post("/api/user/settings")
def update_user_settings(
    req: UserSettingsRequest,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    uid = _uid_from_claims(decoded_token)

    if req.language.lower() in {"hebrew", "il", "israel"} or req.country.upper() == "IL":
        raise HTTPException(status_code=400, detail="Language or country not supported.")

    _ensure_user_firestore(uid)
    _get_user_ref(uid).set(
        {"language": req.language, "country": req.country.upper()},
        merge=True,
    )
    return {
        "status": "success",
        "language": req.language,
        "country": req.country.upper(),
    }


@app.post("/api/user/personality")
def update_personality(
    req: PersonalityRequest,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    uid = _uid_from_claims(decoded_token)
    _ensure_user_firestore(uid)
    _get_user_ref(uid).set({"personality": req.personality}, merge=True)
    return {"status": "success", "personality": req.personality}


@app.post("/api/user/voice")
def update_voice(
    req: VoiceRequest,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    uid = _uid_from_claims(decoded_token)
    _ensure_user_firestore(uid)
    _get_user_ref(uid).set({"voice": req.voice}, merge=True)
    return {"status": "success", "voice": req.voice}


# ---------------------------------------------------------------------------
# Chat sessions/history
# ---------------------------------------------------------------------------

@app.post("/api/session")
def create_session(decoded_token: dict[str, Any] = Depends(get_current_user_token)):
    uid = _uid_from_claims(decoded_token)
    _ensure_user_firestore(
        uid,
        str(decoded_token.get("email") or ""),
        str(decoded_token.get("name") or "User"),
    )
    session_id = str(uuid.uuid4())

    # Create the session document now, so an empty new chat is represented.
    _get_user_ref(uid).collection("chats").document(session_id).set(
        {
            "id": session_id,
            "title": "New chat",
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return {"session_id": session_id}


@app.get("/api/sessions")
def get_user_sessions(decoded_token: dict[str, Any] = Depends(get_current_user_token)):
    uid = _uid_from_claims(decoded_token)
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore is not available")

    chats_ref = (
        _get_user_ref(uid)
        .collection("chats")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(100)
    )

    sessions = []
    for doc in chats_ref.stream():
        data = doc.to_dict() or {}
        data.setdefault("id", doc.id)
        sessions.append(data)
    return sessions


@app.get("/api/chat/history/{session_id}")
def get_chat_history(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    uid = _uid_from_claims(decoded_token)
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore is not available")

    query = (
        _get_user_ref(uid)
        .collection("chats")
        .document(session_id)
        .collection("messages")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    docs = list(query.stream())
    docs.reverse()

    return [
        {
            "role": (doc.to_dict() or {}).get("role"),
            "content": (doc.to_dict() or {}).get("content"),
        }
        for doc in docs
    ]


@app.delete("/api/chat/session/{session_id}")
def delete_chat_session(
    session_id: str,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    uid = _uid_from_claims(decoded_token)
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore is not available")

    chat_ref = _get_user_ref(uid).collection("chats").document(session_id)
    chat_snapshot = chat_ref.get()
    if not chat_snapshot.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    # Firestore batch writes are limited to 500 operations.
    while True:
        docs = list(chat_ref.collection("messages").limit(400).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

    chat_ref.delete()
    return {"status": "success", "message": "Session deleted successfully"}


# ---------------------------------------------------------------------------
# Voice routes
# ---------------------------------------------------------------------------

@app.post("/api/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str | None = None,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    del decoded_token  # Authentication is required; user identity is not needed here.

    if stt_engine is None:
        raise HTTPException(status_code=503, detail="Speech recognition is unavailable")

    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    temp_path: str | None = None

    try:
        content = await audio.read()
        if not content:
            raise HTTPException(status_code=400, detail="Audio file is empty")
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio file is too large")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        # Whisper inference is blocking; keep it off the async event loop.
        text = await asyncio.to_thread(
            stt_engine.transcribe,
            temp_path,
            language=language,
        )
        return {"text": text}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail="Audio transcription failed")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        await audio.close()


@app.get("/api/tts")
async def text_to_speech(
    text: str = Query(min_length=1, max_length=5000),
    voice: str | None = None,
    decoded_token: dict[str, Any] = Depends(get_current_user_token),
):
    del decoded_token
    try:
        preset_names = {"nova", "echo", "alloy", "shimmer", "fable", "onyx"}
        voice_id = None if not voice or voice.lower() in preset_names else voice
        audio_bytes = await generate_speech(text, voice=voice_id)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception:
        logger.exception("Text-to-speech failed")
        raise HTTPException(status_code=500, detail="Speech generation failed")


# Reuse the provider and orchestrator between WebSocket reconnects.
# Gemini is the preferred provider; Groq is only a fallback.
@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    if settings.gemini_api_key:
        provider = GeminiProvider()
    elif settings.groq_api_key:
        provider = GroqProvider()
    else:
        raise RuntimeError("Configure NOT_GEMINI_API_KEY or NOT_GROQ_API_KEY")
    logger.info("NOT AI provider selected: %s", provider.name)
    return Orchestrator(provider)


# ---------------------------------------------------------------------------
# WebSocket chat
# ---------------------------------------------------------------------------

@app.websocket("/ws/{session_id}")
async def ws_chat(
    ws: WebSocket,
    session_id: str,
    token: str | None = Query(default=None),
):
    # Browser WebSocket APIs cannot set Authorization headers. The frontend
    # must pass its Firebase ID token as ?token=<idToken>.
    if not token:
        await ws.close(code=4401, reason="Authentication required")
        return

    try:
        decoded = verify_firebase_token(token)
        uid = _uid_from_claims(decoded)
    except HTTPException:
        await ws.close(code=4401, reason="Invalid authentication")
        return

    if db is None:
        await ws.close(code=1011, reason="Database unavailable")
        return

    # Ensure the requested session belongs to this authenticated user.
    chat_ref = _get_user_ref(uid).collection("chats").document(session_id)
    chat_snapshot = await asyncio.to_thread(chat_ref.get)
    if not chat_snapshot.exists:
        await ws.close(code=4404, reason="Chat session not found")
        return

    await ws.accept()

    try:
        orchestrator = get_orchestrator()

        while True:
            raw = await ws.receive_text()

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON payload"})
                continue

            if not isinstance(payload, dict):
                await ws.send_json({"type": "error", "message": "Invalid message payload"})
                continue

            user_text = str(payload.get("text") or "").strip()
            user_timezone = str(payload.get("timezone") or "UTC")
            user_language = str(payload.get("language") or "en")

            if not user_text:
                continue
            if len(user_text) > 20000:
                await ws.send_json({"type": "error", "message": "Message is too long"})
                continue

            await ws.send_json({"type": "start"})

            # Await the thread call so the save is not silently discarded.
            await asyncio.to_thread(
                _save_message,
                uid,
                session_id,
                "user",
                user_text,
            )

            history = await asyncio.to_thread(
                _load_history_nested,
                uid,
                session_id,
                12,
            )

            full_response = ""

            try:
                async for event in orchestrator.run(
                    history,
                    user_timezone=user_timezone,
                    user_language=user_language,
                ):
                    event_type = event.get("type")

                    if event_type == "token":
                        token_text = str(event.get("text") or "")
                        full_response += token_text
                        await ws.send_json(
                            {"type": "token", "text": token_text}
                        )
                    elif event_type == "camera_request":
                        await ws.send_json(
                            {
                                "type": "camera_request",
                                "prompt": event.get("prompt", ""),
                            }
                        )
                    elif event_type == "error":
                        await ws.send_json(
                            {
                                "type": "error",
                                "message": str(event.get("message") or "AI error"),
                            }
                        )

            except Exception:
                logger.exception("AI generation failed")
                fallback_message = "I couldn't complete that response. Please try again."
                if not full_response:
                    full_response = fallback_message
                    await ws.send_json(
                        {"type": "token", "text": fallback_message}
                    )

            if full_response.strip():
                await asyncio.to_thread(
                    _save_message,
                    uid,
                    session_id,
                    "assistant",
                    full_response,
                )

            await ws.send_json(
                {"type": "end", "content": full_response}
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s", uid)
    except Exception:
        logger.exception("WebSocket runtime error")
        try:
            await ws.send_json(
                {"type": "error", "message": "An internal server error occurred"}
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Frontend routes
# ---------------------------------------------------------------------------

@app.get("/style.css")
def serve_css():
    css_path = FRONTEND_DIR / "css" / "style.css"
    if not css_path.exists():
        css_path = FRONTEND_DIR / "style.css"

    if not css_path.exists():
        raise HTTPException(status_code=404, detail="Stylesheet not found")

    return Response(
        content=css_path.read_text(encoding="utf-8"),
        media_type="text/css",
    )


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>NOT - backend running.</h1>"