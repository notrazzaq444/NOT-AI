"""Firebase Authentication Service."""
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, Header
from typing import Optional
import os

# Admin SDK initialize (ek hi baar)
cred_path = os.path.join(os.path.dirname(__file__), "../../firebase-adminsdk.json")
try:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    print("[Firebase] Admin SDK initialized")
except Exception as e:
    print(f"[Firebase] Init error (maybe already initialized): {e}")

async def verify_firebase_token(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split("Bearer ")[1]
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token invalid: {e}")

async def update_firebase_display_name(uid: str, name: str):
    try:
        auth.update_user(uid, display_name=name)
        return True
    except Exception as e:
        print(f"[Firebase] Update name error: {e}")
        return False