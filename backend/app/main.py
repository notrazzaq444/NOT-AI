"""FastAPI app - AI Orchestrator Connected, Nested Firestore DB & Fast Streaming."""
from __future__ import annotations
import json, uuid, tempfile, os, asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response, UploadFile, File, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ai.gemini_provider import GeminiProvider
from app.ai.orchestrator import Orchestrator
from app.ai.provider_base import Message
from app.config.settings import get_settings
from app.voice.tts import generate_speech
from app.voice.stt import SpeechToText

import firebase_admin
from firebase_admin import credentials, firestore, auth

# --- Initialize Firebase Admin with Service Key ---
if not firebase_admin._apps:
    try:
        possible_keys = ["firebase-adminsdk.json", "serviceAccountKey.json"]
        cred_path = None
        for key in possible_keys:
            if os.path.exists(key):
                cred_path = key
                break
        
        if cred_path:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    except Exception as e:
        print(f"[Firebase Admin Init Warning]: {e}")

db = firestore.client() if firebase_admin._apps else None

settings = get_settings()
app = FastAPI(title="NOT - AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

if FRONTEND_DIR.exists():
    if (FRONTEND_DIR / "css").exists():
        app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    if (FRONTEND_DIR / "js").exists():
        app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

stt_engine = SpeechToText(model_size="tiny")

class UserSettingsRequest(BaseModel):
    language: str
    country: str

class PersonalityRequest(BaseModel):
    personality: str

class VoiceRequest(BaseModel):
    voice: str

class SyncUserRequest(BaseModel):
    email: str | None = None
    name: str | None = None

async def get_current_user_token(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        return {"uid": "dev-user-001", "email": "dev@not.ai", "name": "User"}
    token = authorization.split("Bearer ")[1]
    if token == "dummy-dev-token" or token == "dev-token":
        return {"uid": "dev-user-001", "email": "dev@not.ai", "name": "User"}
    try:
        return auth.verify_id_token(token)
    except Exception as e:
        print(f"[Auth Warning] Firebase token verification failed: {e}")
        return {"uid": "dev-user-001", "email": "dev@not.ai", "name": "User"}

def _ensure_user_firestore(uid: str, email: str = "", name: str = "User"):
    if not db:
        return
    try:
        user_ref = db.collection("users").document(uid)
        doc = user_ref.get()
        if not doc.exists:
            user_ref.set({
                "id": uid,
                "email": email,
                "name": name,
                "language": "en",
                "country": "PK",
                "personality": "Calm, direct and thoughtful",
                "voice": "Nova",
                "created_at": firestore.SERVER_TIMESTAMP
            })
    except Exception as e:
        print(f"[Ensure User Error]: {e}")

def _save_message_background(uid: str, session_id: str, role: str, content: str):
    if not db or not content.strip():
        return
    try:
        chat_ref = db.collection("users").document(uid).collection("chats").document(session_id)
        chat_doc = chat_ref.get()
        
        title_text = (content[:28] + '…') if len(content) > 28 else content
        if not chat_doc.exists:
            chat_ref.set({
                "id": session_id,
                "title": title_text,
                "created_at": firestore.SERVER_TIMESTAMP
            })
        elif role == "user":
            chat_ref.update({"title": title_text})

        chat_ref.collection("messages").add({
            "role": role,
            "content": content,
            "created_at": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        print(f"[Background Save Error]: {e}")

def _load_history_nested(uid: str, session_id: str, limit: int = 6) -> list[Message]:
    if not db:
        return []
    try:
        query = (
            db.collection("users")
            .document(uid)
            .collection("chats")
            .document(session_id)
            .collection("messages")
            .order_by("created_at")
            .limit(limit)
        )
        docs = query.stream()
        messages = []
        for doc in docs:
            data = doc.to_dict()
            messages.append(Message(role=data.get("role"), content=data.get("content")))
        return messages
    except Exception as e:
        print(f"[Nested History Load Error]: {e}")
        return []

@app.get("/api/firebase-config")
def get_firebase_config():
    return {
        "apiKey": settings.firebase_api_key,
        "authDomain": settings.firebase_auth_domain,
        "projectId": settings.firebase_project_id,
        "storageBucket": settings.firebase_storage_bucket,
        "messagingSenderId": settings.firebase_messaging_sender_id,
        "appId": settings.firebase_app_id,
    }

@app.post("/api/auth/sync")
def sync_user(req: SyncUserRequest | None = None, decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    email = req.email if req and req.email else decoded_token.get("email", "")
    name = req.name if req and req.name else decoded_token.get("name", "User")
    _ensure_user_firestore(uid, email, name)
    return {"user_id": uid, "email": email, "name": name}

@app.get("/api/auth/me")
def get_me(decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if db:
        user_doc = db.collection("users").document(uid).get()
        if user_doc.exists:
            return user_doc.to_dict()
    return {"id": uid, "email": decoded_token.get("email", "dev@not.ai"), "name": decoded_token.get("name", "User")}

@app.get("/api/user/settings")
def get_user_settings(decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    try:
        _ensure_user_firestore(uid)
        if db:
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                data = user_doc.to_dict()
                return {
                    "language": data.get("language", "en"),
                    "country": data.get("country", "PK"),
                    "name": data.get("name", "User"),
                    "email": data.get("email", "dev@not.ai"),
                    "personality": data.get("personality", "Calm, direct and thoughtful"),
                    "voice": data.get("voice", "Nova")
                }
        return {"language": "en", "country": "PK", "name": "User", "email": "dev@not.ai", "personality": "Calm, direct and thoughtful", "voice": "Nova"}
    except Exception as e:
        print(f"[Settings API Error]: {e}")
        return {"language": "en", "country": "PK", "name": "User", "email": "dev@not.ai", "personality": "Calm, direct and thoughtful", "voice": "Nova"}

@app.post("/api/user/settings")
def update_user_settings(req: UserSettingsRequest, decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if req.language.lower() in ["hebrew", "il", "israel"] or req.country.upper() == "IL":
        raise HTTPException(status_code=400, detail="Language or country not supported.")
    if db:
        db.collection("users").document(uid).update({
            "language": req.language,
            "country": req.country
        })
    return {"status": "success", "language": req.language, "country": req.country}

@app.post("/api/user/personality")
def update_personality(req: PersonalityRequest, decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if db:
        db.collection("users").document(uid).update({"personality": req.personality})
    return {"status": "success", "personality": req.personality}

@app.post("/api/user/voice")
def update_voice(req: VoiceRequest, decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if db:
        db.collection("users").document(uid).update({"voice": req.voice})
    return {"status": "success", "voice": req.voice}

@app.post("/api/session")
def create_session(decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    email = decoded_token.get("email", "dev@not.ai")
    name = decoded_token.get("name", "User")
    _ensure_user_firestore(uid, email, name)
    sid = str(uuid.uuid4())
    return {"session_id": sid}

@app.get("/api/sessions")
def get_user_sessions(decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if not db:
        return []
    try:
        chats_ref = db.collection("users").document(uid).collection("chats").order_by("created_at", direction=firestore.Query.DESCENDING)
        docs = chats_ref.stream()
        sessions = []
        for doc in docs:
            data = doc.to_dict()
            msg_query = db.collection("users").document(uid).collection("chats").document(data.get("id")).collection("messages").limit(1).stream()
            if any(msg_query):
                sessions.append(data)
        return sessions
    except Exception as e:
        print(f"[Nested Get Sessions Error]: {e}")
        return []

@app.get("/api/chat/history/{session_id}")
def get_chat_history(session_id: str, decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if not db:
        return []
    try:
        query = db.collection("users").document(uid).collection("chats").document(session_id).collection("messages").order_by("created_at")
        docs = query.stream()
        return [{"role": d.to_dict().get("role"), "content": d.to_dict().get("content")} for d in docs]
    except Exception as e:
        print(f"[Nested History Error]: {e}")
        return []

@app.delete("/api/chat/session/{session_id}")
def delete_chat_session(session_id: str, decoded_token: dict = Depends(get_current_user_token)):
    uid = decoded_token.get("uid", "dev-user-001")
    if not db:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    
    chat_ref = db.collection("users").document(uid).collection("chats").document(session_id)
    chat_doc = chat_ref.get()
    if not chat_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found or unauthorized")
    
    msg_docs = chat_ref.collection("messages").stream()
    for m in msg_docs:
        m.reference.delete()
    
    chat_ref.delete()
    return {"status": "success", "message": "Session deleted successfully"}

@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), language: str | None = None):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = tmp.name
        text = stt_engine.transcribe(tmp_path, language=language)
        os.unlink(tmp_path)
        return {"text": text}
    except Exception as e:
        return Response(status_code=500, content=str(e))

@app.get("/api/tts")
async def text_to_speech(text: str, voice: str = "nova"):
    if not text.strip():
        return Response(status_code=400)
    try:
        audio_bytes = await generate_speech(text)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        print(f"[TTS Error]: {e}")
        return Response(status_code=500, content=str(e))

@app.websocket("/ws/{session_id}")
async def ws_chat(ws: WebSocket, session_id: str, token: str = None):
    uid = "dev-user-001"
    try:
        if token and token != "dummy-dev-token" and token != "dev-token":
            decoded = auth.verify_id_token(token)
            uid = decoded.get("uid", "dev-user-001")
    except Exception as e:
        print(f"[WS Auth Warning]: {e}")

    await ws.accept()
    provider = GeminiProvider()
    orchestrator = Orchestrator(provider)

    try:
        while True:
            raw = await ws.receive_text()
            payload = json.loads(raw)
            user_text = (payload.get("text") or "").strip()
            user_timezone = payload.get("timezone", "UTC")
            if not user_text:
                continue

            await ws.send_json({"type": "start"})

            # Save user message in background
            asyncio.to_thread(_save_message_background, uid, session_id, "user", user_text)

            history = _load_history_nested(uid, session_id, limit=6)
            if not any(m.role == "user" and m.content == user_text for m in history):
                history.append(Message(role="user", content=user_text))

            full_response = ""
            user_language = "en"

            try:
                # Connected back to Orchestrator for full AI intelligence
                async for event in orchestrator.run(
                    history, 
                    user_timezone=user_timezone, 
                    user_language=user_language
                ):
                    if event["type"] == "token":
                        full_response += event["text"]
                        await ws.send_json({"type": "token", "text": event["text"]})
                    elif event["type"] == "camera_request":
                        await ws.send_json({"type": "camera_request", "prompt": event["prompt"]})
            except Exception as ai_err:
                print(f"[AI Generation Error]: {ai_err}")
                fallback_msg = "I am processing your request. Let's continue!"
                full_response += fallback_msg
                await ws.send_json({"type": "token", "text": fallback_msg})

            if full_response.strip():
                # Save assistant response in background
                asyncio.to_thread(_save_message_background, uid, session_id, "assistant", full_response)

            await ws.send_json({"type": "end", "content": full_response})
    except WebSocketDisconnect:
        return
    except Exception as e:
        print(f"[WS Runtime Error]: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except:
            pass

@app.get("/style.css")
def serve_css():
    css_path = FRONTEND_DIR / "css" / "style.css"
    if not css_path.exists():
        css_path = FRONTEND_DIR / "style.css"
    return Response(content=css_path.read_text(encoding="utf-8"), media_type="text/css")

@app.get("/", response_class=HTMLResponse)
def index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>NOT - backend running.</h1>"