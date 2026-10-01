# auth_service.py
import os, requests
from fastapi import Header, HTTPException

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")

def get_current_user(authorization: str = Header(None)):
    """
    Reads the 'Authorization: Bearer <token>' header from the request,
    asks Supabase 'is this token real, and who does it belong to?'
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.replace("Bearer ", "")

    response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": SUPABASE_PUBLISHABLE_KEY
        }
    )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_data = response.json()
    return user_data["id"]  # this is the real, verified user_id