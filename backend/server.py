from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, Header, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import logging
import uuid
import asyncio
import httpx
import base64
import secrets
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from collections import deque
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

# --- RATE LIMITING & CACHING ---
class RateLimiter:
    def __init__(self, requests_limit: int, window_seconds: int):
        self.limit = requests_limit
        self.window = window_seconds
        self.history = {} # {ip: deque([timestamps])}

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        if client_id not in self.history:
            self.history[client_id] = deque()
        
        # Remove old timestamps
        while self.history[client_id] and self.history[client_id][0] < now - self.window:
            self.history[client_id].popleft()
            
        if len(self.history[client_id]) < self.limit:
            self.history[client_id].append(now)
            return True
        return False

# Global limiters
api_limiter = RateLimiter(60, 60) # 60 requests per minute
track_limiter = RateLimiter(120, 60) # 120 pixel hits per minute

# Simple Auth Cache
AUTH_CACHE = {} # {token: {"user": dict, "expiry": timestamp}}
CACHE_TTL = 300 # 5 minutes

def get_next_business_time(dt: datetime, offset: int, unit: str = "days", target_hour: Optional[int] = None):
    """Calculates the next scheduled time, skipping weekends.
    unit: 'days' or 'hours'
    On weekdays: preserves exact minutes/seconds unless a target_hour is provided.
    On weekends: shifts to Monday at exactly 10:00 AM."""
    if unit == "hours":
        target = dt + timedelta(hours=offset)
    else:
        target = dt + timedelta(days=offset)
    
    # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    if target.weekday() >= 5: # Saturday or Sunday
        days_to_monday = (7 - target.weekday()) % 7
        target = target + timedelta(days=days_to_monday)
        # Shift to exactly 10 AM Monday
        target = target.replace(hour=10, minute=0, second=0, microsecond=0)
    elif target_hour is not None and unit == "days":
        # Override the hour only for 'days' unit
        target = target.replace(hour=target_hour)
    
    return target


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()

# --- CORS CONFIGURATION ---
# Robust origin parsing (handles spaces, newlines, and trailing slashes)
raw_origins = os.environ.get("CORS_ORIGINS", "")
cors_origins = [o.strip().rstrip("/") for o in raw_origins.replace("\n", ",").split(",") if o.strip()]

# DEBUG: Print origins in Render logs to verify
print(f"CORS Origins: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"chrome-extension://.*|moz-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"422 Validation Error at {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

# Explicit OPTIONS handler to prevent 400 on Preflight
@app.options("/api/auth/google-native")
async def options_google_native():
    return Response(status_code=200)

async def get_user_by_ext_key(request: Request) -> dict:
    x_ext_key = request.headers.get("X-Ext-Key") or request.query_params.get("key")
    if not x_ext_key:
        raise HTTPException(status_code=401, detail="Missing extension key")
    user = await db.users.find_one({"ext_api_key": x_ext_key}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid extension key")
    return user

async def get_user_any_auth(request: Request) -> dict:
    """Attempts session auth first, then falls back to extension key auth."""
    # Try session auth (Authorization: Bearer <token>)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            return await get_current_user(request)
        except Exception:
            pass
            
    # Try extension key auth
    try:
        return await get_user_by_ext_key(request)
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

# No prefix here because it's added during include_router at the bottom
api_router = APIRouter()


@api_router.get("/ext-profile")
async def ext_profile(user: dict = Depends(get_user_by_ext_key)):
    return {
        "email": user["email"],
        "name": user["name"]
    }

# 1x1 transparent PNG bytes
PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

# In-memory pub/sub for SSE notifications (per-user open events)
event_queues: Dict[str, List[asyncio.Queue]] = {}

def push_event(user_id: str, payload: dict):
    queues = event_queues.get(user_id, [])
    for q in queues:
        try:
            q.put_nowait(payload)
        except Exception:
            pass

# ---------- Models ----------
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    ext_api_key: str

class TrackCreate(BaseModel):
    recipient: str
    subject: str
    message_preview: Optional[str] = ""

class TrackedEmail(BaseModel):
    id: str
    user_id: str
    recipient: str
    subject: str
    message_preview: Optional[str] = ""
    sent_at: str
    open_count: int = 0
    last_opened_at: Optional[str] = None
    opens: List[Dict[str, Any]] = []
    replied: bool = False
    follow_up_count: int = 0

class FollowUpCreate(BaseModel):
    tracked_email_id: str
    message: str
    days_delay: int = 3
    mode: str = "manual"  # 'manual' or 'auto'
    trigger_condition: str = "always" # 'always', 'if_not_opened', 'if_not_replied'

class FollowUp(BaseModel):
    id: str
    user_id: str
    tracked_email_id: str
    recipient: str
    subject: str
    message: str
    days_delay: Optional[int] = None # backward compatibility
    delay_value: Optional[int] = None
    delay_unit: str = "days"
    sequence_order: int = 0  # NEW: Step 1, 2, 3...
    scheduled_at: str
    mode: str
    sent: bool = False
    completed: bool = False  # NEW: True once dispatched
    sent_at: Optional[str] = None
    trigger_condition: str = "always"
    repeated_followup: bool = False  # NEW: True if resending last stage
    repeated_cycle: int = 0  # NEW: 1, 2, 3...
    open_count: int = 0
    opens: List[Dict[str, Any]] = []
    time: Optional[str] = None

class AutomationStage(BaseModel):
    trigger: str
    delay_value: Optional[int] = None
    days: Optional[int] = None # backward compatibility
    delay_unit: str = "days" # 'days' or 'hours'
    time: str # 'HH:MM'
    message: str

class AutomationRuleCreate(BaseModel):
    name: str
    stages: List[AutomationStage]
    repeat_last: bool = False # NEW: Whether to repeat the final stage

class AutomationRule(BaseModel):
    id: str
    user_id: str
    name: str
    stages: List[AutomationStage]
    repeat_last: bool = False # NEW
    created_at: str

# --- PERSISTENT TASK QUEUE MODELS ---
class Task(BaseModel):
    id: str
    user_id: str
    type: str # 'send_fup', 'check_reply', 'maintenance'
    payload: dict
    status: str = "pending" # 'pending', 'running', 'completed', 'failed'
    scheduled_at: str
    created_at: str
    retries: int = 0
    max_retries: int = 3
    error_log: List[str] = []

# ---------- Auth helpers ----------
async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    token = request.cookies.get("session_token")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check Cache
    now = time.time()
    if token in AUTH_CACHE:
        entry = AUTH_CACHE[token]
        if now < entry["expiry"]:
            return entry["user"]
    
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    expires_at = sess["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
        
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    # Save to Cache
    AUTH_CACHE[token] = {"user": user, "expiry": now + CACHE_TTL}
    return user

# ---------- Auth endpoints ----------
class GoogleAuth(BaseModel):
    token: str

@api_router.post("/auth/google")
async def auth_google(payload: GoogleAuth, response: Response):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Backend GOOGLE_CLIENT_ID not configured in .env")

    try:
        # Verify the JWT token from Google
        idinfo = id_token.verify_oauth2_token(
            payload.token, 
            google_requests.Request(), 
            client_id
        )
        
        email = idinfo["email"]
        name = idinfo.get("name", email)
        picture = idinfo.get("picture")
        
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")

class GoogleNativeAuth(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None

@api_router.post("/auth/google-native")
async def auth_google_native(payload: dict, response: Response):
    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required")

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth credentials not configured")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_res = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "postmessage",
            "grant_type": "authorization_code"
        })
        if token_res.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Failed to exchange token: {token_res.text}")
            
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        # Fetch user info
        user_res = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={
            "Authorization": f"Bearer {access_token}"
        })
        if user_res.status_code != 200:
            raise HTTPException(status_code=401, detail="Failed to fetch user info")
            
        user_info = user_res.json()
        email = user_info.get("email")
        name = user_info.get("name") or email
        picture = user_info.get("picture")

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        ext_api_key = existing.get("ext_api_key") or secrets.token_urlsafe(24)
        update_data = {
            "name": name, 
            "picture": picture, 
            "ext_api_key": ext_api_key,
            "access_token": access_token
        }
        if refresh_token:
            update_data["refresh_token"] = refresh_token
            
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": update_data},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        ext_api_key = secrets.token_urlsafe(24)
        new_user = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "ext_api_key": ext_api_key,
            "access_token": access_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if refresh_token:
            new_user["refresh_token"] = refresh_token
        await db.users.insert_one(new_user)

    session_token = secrets.token_urlsafe(32)
    # Long-lived session (1 year) for persistence
    expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # On localhost (HTTP) secure=True blocks the cookie. Detect environment.
    # Better way to detect if we are on Render production vs Localhost
    is_production = os.environ.get("RENDER") is not None or "localhost" not in os.environ.get("BACKEND_URL", "localhost")
    
    response.set_cookie(
        "session_token", session_token,
        httponly=True,
        secure=is_production,
        samesite="none" if is_production else "lax",
        max_age=365 * 24 * 60 * 60, # 1 year in seconds
        path="/",
    )

    return {
        "user_id": user_id, "email": email, "name": name,
        "picture": picture, "ext_api_key": ext_api_key,
    }


@api_router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user["user_id"], "email": user["email"],
        "name": user["name"], "picture": user.get("picture"),
        "ext_api_key": user["ext_api_key"],
    }

@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}

@api_router.post("/auth/rotate-ext-key")
async def rotate_ext_key(user: dict = Depends(get_current_user)):
    new_key = secrets.token_urlsafe(24)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"ext_api_key": new_key}})
    return {"ext_api_key": new_key}

# ---------- Tracking ----------
def get_client_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip", "").strip()
        or request.headers.get("x-real-ip", "").strip()
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )

@api_router.post("/track/create")
async def create_tracked(payload: TrackCreate, request: Request, user: dict = Depends(get_user_by_ext_key)):
    tid = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    sender_ip = get_client_ip(request)
    doc = {
        "id": tid,
        "user_id": user["user_id"],
        "recipient": payload.recipient,
        "subject": payload.subject,
        "message_preview": payload.message_preview or "",
        "sent_at": now,
        "last_activity_at": now,
        "status": "draft",
        "sender_ip": sender_ip,
        "open_count": 0,
        "scan_count": 0,
        "last_opened_at": None,
        "opens": [],
        "scans": [],
        "replied": False,
        "follow_up_count": 0,
    }
    await db.tracked_emails.insert_one(doc)

    # --- INSTANT AUTOMATION SCHEDULING ---
    # We schedule the sequence NOW so the countdown is ready immediately.
    try:
        rules = await db.automation_rules.find({"user_id": user["user_id"]}).to_list(100)
        if rules:
            now_dt = datetime.now(timezone.utc)
            for rule in rules:
                rule_name = rule.get("name", "Unnamed Rule")
                all_stages = rule.get("stages", [])
                if not all_stages: continue
                
                # ONLY schedule the FIRST stage upfront. 
                # Subsequent stages will be cascaded by the automation_worker once the previous one is sent.
                stage = all_stages[0]
                
                trigger = stage.get("trigger", "no_reply")
                if trigger == "no_open": cond = "if_no_open"
                elif trigger == "opened_no_reply": cond = "if_opened_no_reply"
                else: cond = f"if_{trigger}"
                
                # Only schedule no_open stages upfront
                if cond != "if_no_open":
                    continue

                try:
                    time_val = stage.get("time")
                    val = stage.get("delay_value", 1)
                    unit = stage.get("delay_unit", "days")
                    hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else None
                    scheduled = get_next_business_time(now_dt, val, unit=unit, target_hour=hour)
                except:
                    scheduled = now_dt + timedelta(days=stage.get("delay_value", 1))

                await _create_fup(
                    tid, stage["message"], stage.get("delay_value", 1), stage.get("delay_unit", "days"), "auto", cond, user["user_id"],
                    custom_scheduled_at=scheduled, time=stage.get("time"),
                    sequence_order=1
                )
                logging.info(f"Instantly scheduled Stage 1 of '{rule_name}' for tracking ID: {tid}")
    except Exception as e:
        logging.error(f"Instant schedule failed for {tid}: {e}")

    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    base = f"{proto}://{host}" if host else ""
    return {
        "id": tid,
        "pixel_url": f"{base}/api/track/pixel/{tid}.png" if base else f"/api/track/pixel/{tid}.png",
    }

class TrackUpdate(BaseModel):
    recipient: Optional[str] = None
    subject: Optional[str] = None
    message_preview: Optional[str] = None

@api_router.post("/track/update/{tid}")
async def update_tracked(tid: str, payload: TrackUpdate, user: dict = Depends(get_user_any_auth)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["status"] = "sent"
    now = datetime.now(timezone.utc).isoformat()
    updates["sent_at"] = now
    updates["last_activity_at"] = now
    em = await db.tracked_emails.find_one({"id": tid, "user_id": user["user_id"]}, {"_id": 0})
    if not em:
        raise HTTPException(404, "Email record not found")

    if updates:
        await db.tracked_emails.update_one(
            {"id": tid, "user_id": user["user_id"]},
            {"$set": updates},
        )
        logging.info(f"Email {tid} updated to 'sent' status. Checking for automation...")
        
        # Apply Automation Sequences
        # Avoid duplicate scheduling if follow-ups already exist for this TID
        # Update existing follow-ups with the best available metadata
        new_rcpt = updates.get("recipient")
        new_subj = updates.get("subject")
        
        # Only overwrite if we have better data than the current follow-up has
        fup_update = {}
        if new_rcpt and "unknown" not in new_rcpt.lower():
            fup_update["recipient"] = new_rcpt
        elif em.get("recipient") and "unknown" not in em.get("recipient").lower():
            fup_update["recipient"] = em["recipient"]
            
        if new_subj and new_subj != "(draft)":
            fup_update["subject"] = new_subj
        elif em.get("subject") and em.get("subject") != "(draft)":
            fup_update["subject"] = em["subject"]

        if fup_update:
            await db.follow_ups.update_many(
                {"tracked_email_id": tid, "user_id": user["user_id"]},
                {"$set": fup_update}
            )
        
        sent_at_dt = datetime.now(timezone.utc)
        
        # Get existing follow-up stages to avoid duplicates
        existing_fups = await db.follow_ups.find({"tracked_email_id": tid, "user_id": user["user_id"]}).to_list(100)
        existing_delays = { (f.get("delay_value"), f.get("delay_unit", "days"), f["trigger_condition"]) for f in existing_fups }

        # Apply Automation Sequences
        rules = await db.automation_rules.find({"user_id": user["user_id"]}).to_list(100)
        
        if not rules:
            logging.warning(f"No automation rules found for user {user['user_id']}. Cannot schedule follow-ups.")
            return {"ok": True}
        
        logging.info(f"Applying all active rules to email {tid}")
        
        for rule in rules:
            rule_name = rule.get("name", "Unnamed Rule")
            all_stages = rule.get("stages", [])
            if not all_stages: continue

            # ONLY schedule the FIRST stage upfront. 
            stage = all_stages[0]
            
            trigger = stage.get("trigger", "no_reply")
            if trigger == "no_open": cond = "if_no_open"
            elif trigger == "opened_no_reply": cond = "if_opened_no_reply"
            else: cond = f"if_{trigger}"
            
            # Use business time logic if hours are provided, else simple days
            try:
                time_val = stage.get("time")
                val = stage.get("delay_value", 1)
                unit = stage.get("delay_unit", "days")
                hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else None
                scheduled = get_next_business_time(sent_at_dt, val, unit=unit, target_hour=hour)
            except Exception:
                scheduled = sent_at_dt + timedelta(days=stage.get("delay_value", 1))

            # Only schedule missing 'no_open' stages upfront
            if cond == "if_no_open" and (val, unit, cond) not in existing_delays:
                await _create_fup(
                    tid, 
                    stage["message"], 
                    val, 
                    unit,
                    "auto", 
                    cond, 
                    user["user_id"],
                    custom_scheduled_at=scheduled,
                    time=stage.get("time"),
                    sequence_order=1
                )
                logging.info(f"Scheduled Stage 1 from '{rule_name}' ({cond}, {val} {unit}) for {tid}")
            elif (val, unit, cond) in existing_delays:
                # Update existing one's schedule for precision relative to final sent time
                await db.follow_ups.update_one(
                    {"tracked_email_id": tid, "delay_value": val, "delay_unit": unit, "trigger_condition": cond, "sent": False},
                    {"$set": {"scheduled_at": scheduled.isoformat()}}
                )

        return {"ok": True}

class HeartbeatViewing(BaseModel):
    tracked_ids: List[str]

@api_router.post("/track/{tid}/mark-replied")
async def mark_replied(tid: str, user: dict = Depends(get_user_by_ext_key)):
    """Extension or Dashboard calls this to mark replied and stop sequences.
    Verified against Gmail API to avoid false positives."""
    
    # 1. Server-side verification using Gmail API
    if user.get("access_token"):
        em = await db.tracked_emails.find_one({"id": tid, "user_id": user["user_id"]})
        if em:
            # Find the thread
            tgid, _ = await find_thread_info(user["access_token"], em["recipient"], em["subject"])
            if not tgid:
                logging.info(f"Reply detection deferred for {tid} (Thread not indexed yet)")
                return {"ok": True, "verified": False, "status": "indexing"}

            url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{tgid}"
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers={"Authorization": f"Bearer {user['access_token']}"})
                if r.status_code == 200:
                    thread_data = r.json()
                    messages = thread_data.get("messages", [])
                    
                    found_real_reply = False
                    my_email = user["email"].lower()
                    for m in messages:
                        headers = m.get("payload", {}).get("headers", [])
                        from_h = next((h["value"].lower() for h in headers if h["name"].lower() == "from"), "")
                        if from_h and my_email not in from_h:
                            found_real_reply = True
                            break
                    
                    if not found_real_reply:
                        logging.info(f"Rejected false reply detection for {tid} (Verified: only sender spoke)")
                        return {"ok": True, "verified": False, "status": "ignored"}
                else:
                    # Token might be expired or API down
                    return {"ok": True, "verified": False, "status": "api_error"}

    # 2. Proceed to mark as replied (if verified or if we don't have Gmail access to verify)
    await db.tracked_emails.update_one(
        {"id": tid, "user_id": user["user_id"]},
        {"$set": {"replied": True}}
    )
    # Stop pending follow-ups
    await stop_sequences(tid, user["user_id"])
    return {"ok": True, "verified": True}

@api_router.get("/emails/active")
async def list_active_mails(page: int = 1, limit: int = 10, user: dict = Depends(get_current_user)):
    """Return only emails that have been replied to, with pagination."""
    skip = (page - 1) * limit
    cursor = db.tracked_emails.find({"user_id": user["user_id"], "replied": True}, {"_id": 0})
    total = await db.tracked_emails.count_documents({"user_id": user["user_id"], "replied": True})
    
    items = await cursor.sort("last_activity_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }

@api_router.get("/emails/by-ext")
async def list_emails_ext(user: dict = Depends(get_user_by_ext_key)):
    """Extension calls this to get all tracked emails for ticks."""
    cursor = db.tracked_emails.find({"user_id": user["user_id"]}, {"_id": 0})
    return await cursor.sort("sent_at", -1).to_list(1000)


    



@api_router.post("/track/heartbeat-viewing")
async def heartbeat_viewing(payload: HeartbeatViewing, user: dict = Depends(get_user_by_ext_key)):
    """Bulk mark-viewing: extension sends list of currently-visible tracked email IDs
    in the user's Gmail. All get a 30-second self-view window (rolling, refreshed on
    each heartbeat). Also retroactively reclassifies last 30s opens as scans."""
    if not payload.tracked_ids:
        return {"ok": True, "marked": 0}
    now = datetime.now(timezone.utc)
    until = (now + timedelta(seconds=30)).isoformat()
    cutoff = (now - timedelta(seconds=30)).isoformat()

    rows = await db.tracked_emails.find(
        {"id": {"$in": payload.tracked_ids}, "user_id": user["user_id"]}, {"_id": 0}
    ).to_list(200)
    moved_total = 0
    for em in rows:
        opens = em.get("opens", [])
        scans = em.get("scans", [])
        keep_opens = []
        for o in opens:
            if o.get("ts", "") >= cutoff:
                scans.append({**o, "self_view_retro": True})
                moved_total += 1
            else:
                keep_opens.append(o)
        last_opened = keep_opens[-1]["ts"] if keep_opens else None
        await db.tracked_emails.update_one(
            {"id": em["id"]},
            {"$set": {
                "self_viewing_until": until,
                "opens": keep_opens,
                "open_count": len(keep_opens),
                "last_opened_at": last_opened,
                "scans": scans,
                "scan_count": len(scans),
            }},
        )
    return {"ok": True, "marked": len(rows), "moved_to_scans": moved_total}

@api_router.post("/track/{tid}/mark-viewing")
async def mark_viewing(tid: str, user: dict = Depends(get_user_by_ext_key)):
    """Extension calls this when user opens their own tracked email in Gmail.
    Sets self_viewing_until = now + 4s (forward filter). Reduced further to allow 
    lightning-fast local cross-account testing without blocking genuine opens."""
    now = datetime.now(timezone.utc)
    until = (now + timedelta(seconds=4)).isoformat()

    await db.tracked_emails.update_one(
        {"id": tid, "user_id": user["user_id"]},
        {"$set": {
            "self_viewing_until": until,
        }},
    )
    return {"ok": True, "self_viewing_until": until}


class NotifiedUpdate(BaseModel):
    count: int

@api_router.post("/track/{tid}/mark-notified")
async def mark_notified(tid: str, update: NotifiedUpdate, user: dict = Depends(get_user_by_ext_key)):
    """Extension calls this to record that it has shown a desktop notification up to a certain open count."""
    await db.tracked_emails.update_one(
        {"id": tid, "user_id": user["user_id"]},
        {"$set": {"notified_count": update.count}}
    )
    return {"ok": True}


@api_router.post("/track/{tid}/extension-open")
async def extension_assisted_open(tid: str, request: Request, user: dict = Depends(get_user_by_ext_key)):
    """Extension calls this when it detects a tracked email being opened. 
    This completely bypasses Google Image Proxy caching, allowing 100% accurate multiple opens 
    if the recipient has the extension installed."""
    em = await db.tracked_emails.find_one({"id": tid}, {"_id": 0})
    if not em:
        return {"ok": False}
        
    # If the user making this request is the sender of the email, DO NOT count it!
    if em.get("user_id") == user.get("user_id"):
        return {"ok": "self_viewing_sender"}
        
    now = datetime.now(timezone.utc)
    # Debounce 1 second to prevent double-counting with the initial GIP proxy hit
    last_opened = em.get("last_opened_at")
    if last_opened:
        last_dt = datetime.fromisoformat(last_opened) if isinstance(last_opened, str) else last_opened
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        if (now - last_dt).total_seconds() < 1:
            return {"ok": "debounced"}
            
    ts = now.isoformat()
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "extension-assisted")
    
    # Do not count if sender is viewing their own sent mail
    self_viewing_raw = em.get("self_viewing_until")
    if self_viewing_raw:
        until = datetime.fromisoformat(self_viewing_raw) if isinstance(self_viewing_raw, str) else self_viewing_raw
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until > now:
            return {"ok": "self_viewing"}
            
    # Record it
    await db.tracked_emails.update_one(
        {"id": tid},
        {
            "$inc": {"open_count": 1},
            "$set": {"last_opened_at": ts, "last_activity_at": ts},
            "$push": {"opens": {"ts": ts, "ua": ua, "ip": ip}},
        }
    )
    
    # Push notification for every open, with a 10-second debounce
    last_notified = em.get("last_notified_at")
    should_notify = True
    if last_notified:
        last_dt = datetime.fromisoformat(last_notified)
        if last_dt.tzinfo is None: last_dt = last_dt.replace(tzinfo=timezone.utc)
        if (now - last_dt).total_seconds() < 10:
            should_notify = False
            
    if should_notify:
        await db.tracked_emails.update_one({"id": tid}, {"$set": {"last_notified_at": ts}})
        push_event(em["user_id"], {
            "type": "open",
            "tracked_id": tid,
            "recipient": em["recipient"],
            "subject": em["subject"],
            "ts": ts
        })

        # --- DYNAMIC RESCHEDULING ---
        # 1. ALWAYS delete any pending "no open" follow-ups when an open occurs
        deleted = await db.follow_ups.delete_many({
            "tracked_email_id": tid,
            "sent": False,
            "trigger_condition": {"$in": ["if_no_open", "if_not_opened"]}
        })
        if deleted.deleted_count > 0:
            logging.info(f"Deleted {deleted.deleted_count} 'no open' follow-ups for {tid} because of extension-open")

        # 2. Reschedule "opened but no reply" follow-ups relative to NOW
        existing_opened = await db.follow_ups.find_one({
            "tracked_email_id": tid,
            "trigger_condition": "if_opened_no_reply"
        })
        
        if existing_opened:
            if not existing_opened.get("sent"):
                # Reschedule existing one relative to MAIN SENT TIME
                sent_at_raw = em.get("sent_at")
                sent_at = datetime.fromisoformat(sent_at_raw) if isinstance(sent_at_raw, str) else sent_at_raw
                if sent_at and sent_at.tzinfo is None: sent_at = sent_at.replace(tzinfo=timezone.utc)
                
                delay = existing_opened.get("days_delay", 1)
                # Use same hour as main mail
                new_sched = get_next_business_time(sent_at, delay, target_hour=sent_at.hour)
                await db.follow_ups.update_one(
                    {"id": existing_opened["id"]},
                    {"$set": {"scheduled_at": new_sched.isoformat()}}
                )
                logging.info(f"Rescheduled existing FUP relative to sent_at for {tid}")
        else:
            # 3. PROACTIVE FETCH: Schedule ALL 'opened_no_reply' stages for the sequence
            rules = await db.automation_rules.find({"user_id": user["user_id"]}).sort([("updated_at", -1), ("created_at", -1)]).to_list(1)
            
            if rules:
                all_stages = rules[0].get("stages", [])
                open_stages = [s for s in all_stages if s.get("trigger") in ["opened_no_reply", "no_reply"]]
                
                sent_at_raw = em.get("sent_at")
                sent_at = datetime.fromisoformat(sent_at_raw) if isinstance(sent_at_raw, str) else sent_at_raw
                if sent_at and sent_at.tzinfo is None: sent_at = sent_at.replace(tzinfo=timezone.utc)

                for stage in open_stages:
                    delay = stage.get("days", 1)
                    time_val = stage.get("time")
                    hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else sent_at.hour
                    new_sched = get_next_business_time(sent_at, delay, target_hour=hour)
                    
                    await _create_fup(tid, stage["message"], delay, "auto", "if_opened_no_reply", user["user_id"], custom_scheduled_at=new_sched, time=time_val)
                    logging.info(f"Proactively scheduled 'opened_no_reply' stage (Day {delay}) for {tid}")
    return {"ok": True}

@api_router.get("/emails/{tid}")
async def get_email_detail(tid: str, user: dict = Depends(get_current_user)):
    em = await db.tracked_emails.find_one({"id": tid, "user_id": user["user_id"]}, {"_id": 0})
    if not em: raise HTTPException(404)
    fups = await db.follow_ups.find({"tracked_email_id": tid}, {"_id": 0}).sort("scheduled_at", 1).to_list(100)
    return {**em, "follow_ups": fups}


@api_router.get("/track/pixel/{tid}.png")
async def track_pixel(tid: str, request: Request):
    """The heart of the tracking system. Serves a 1x1 pixel and records the open."""
    # 1. Identify if this is a follow-up or a main email
    is_fup = False
    original_tid = tid
    fup = await db.follow_ups.find_one({"id": tid})
    if fup:
        is_fup = True
        original_tid = fup["tracked_email_id"]

    em = await db.tracked_emails.find_one({"id": original_tid})
    if not em:
        return Response(content=PIXEL_PNG, media_type="image/png")

    # Ignore draft loads
    if em.get("status") == "draft":
        return Response(content=PIXEL_PNG, media_type="image/png")

    # Check if there is a newer email sent to the same recipient.
    # If so, we sleep longer to let the newer email register its open first!
    newer_exists = False
    if em.get("recipient") and em.get("sent_at"):
        newer_exists_doc = await db.tracked_emails.find_one({
            "user_id": em.get("user_id"),
            "recipient": em.get("recipient"),
            "sent_at": {"$gt": em.get("sent_at")}
        })
        if newer_exists_doc:
            newer_exists = True

    # Wait for extension to ping /mark-viewing
    await asyncio.sleep(4.0 if newer_exists else 2.0)
    
    # Re-fetch for updated self-viewing flags
    em = await db.tracked_emails.find_one({"id": original_tid})
    if not em: return Response(content=PIXEL_PNG, media_type="image/png")

    ts = datetime.now(timezone.utc).isoformat()
    ua = request.headers.get("user-agent", "")
    ip = get_client_ip(request)

    # Self-view protection
    until_str = em.get("self_viewing_until")
    is_self_viewing = False
    if until_str:
        until_dt = datetime.fromisoformat(until_str)
        if until_dt.tzinfo is None: until_dt = until_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < until_dt:
            is_self_viewing = True

    sent_at_raw = em.get("sent_at")
    sent_at = datetime.fromisoformat(sent_at_raw) if isinstance(sent_at_raw, str) else sent_at_raw
    if sent_at and sent_at.tzinfo is None: sent_at = sent_at.replace(tzinfo=timezone.utc)
    seconds_since_send = (datetime.now(timezone.utc) - sent_at).total_seconds() if sent_at else 9999

    scanner_ip_prefixes = ("66.249.", "64.233.", "209.85.", "72.14.", "216.58.", "172.217.")
    is_google_scanner_ip = ip.startswith(scanner_ip_prefixes) if ip else False
    is_image_proxy = ("GoogleImageProxy" in ua) or ("ggpht.com" in ua)

    is_thread_preload = False
    if newer_exists:
        newer_opened = await db.tracked_emails.find_one({
            "user_id": em.get("user_id"),
            "recipient": em.get("recipient"),
            "sent_at": {"$gt": em.get("sent_at")},
            "last_opened_at": {"$exists": True}
        }, sort=[("last_opened_at", -1)])
        
        if newer_opened and newer_opened.get("last_opened_at"):
            last_op = datetime.fromisoformat(newer_opened["last_opened_at"])
            if last_op.tzinfo is None: last_op = last_op.replace(tzinfo=timezone.utc)
            # If a newer email to the same recipient was opened within the last 15 seconds,
            # this is almost certainly a Gmail thread expansion preload. Suppress it!
            if (datetime.now(timezone.utc) - last_op).total_seconds() < 15:
                is_thread_preload = True

    is_scan = (
        seconds_since_send < 2 
        or is_self_viewing 
        or (em.get("sender_ip") and ip == em.get("sender_ip")) # IP-based self-view protection
        or (is_google_scanner_ip and not is_image_proxy)
        or is_thread_preload
        or "Google-Read-Aloud" in ua
    )

    collection = db.follow_ups if is_fup else db.tracked_emails

    if is_scan:
        await collection.update_one({"id": tid}, {
            "$inc": {"scan_count": 1},
            "$push": {"scans": {"ts": ts, "ua": ua, "ip": ip}}
        })
    else:
        await collection.update_one({"id": tid}, {
            "$inc": {"open_count": 1},
            "$set": {"last_opened_at": ts, "last_activity_at": ts},
            "$push": {"opens": {"ts": ts, "ua": ua, "ip": ip}}
        })
        # Push notification for every open, with a 10-second debounce
        last_notified = em.get("last_notified_at")
        should_notify = True
        now_dt = datetime.now(timezone.utc)
        if last_notified:
            ln_dt = datetime.fromisoformat(last_notified)
            if (now_dt - ln_dt.replace(tzinfo=timezone.utc)).total_seconds() < 10:
                should_notify = False

        if should_notify:
            await db.tracked_emails.update_one({"id": original_tid}, {"$set": {"last_notified_at": ts}})
            push_event(em["user_id"], {
                "type": "open",
                "tracked_id": tid,
                "recipient": em["recipient"],
                "subject": em["subject"],
                "ts": ts,
                "is_followup": is_fup
            })

        # --- DYNAMIC RESCHEDULING ---
        # 1. ALWAYS delete any pending "no open" follow-ups when an open occurs
        deleted = await db.follow_ups.delete_many({
            "tracked_email_id": original_tid,
            "sent": False,
            "trigger_condition": {"$in": ["if_no_open", "if_not_opened"]}
        })
        if deleted.deleted_count > 0:
            logging.info(f"Deleted {deleted.deleted_count} 'no open' follow-ups for {original_tid} because of pixel-open")

        # 2. Reschedule or Create "opened but no reply" follow-ups
        pending_opened = await db.follow_ups.find_one({
            "tracked_email_id": original_tid,
            "sent": False,
            "trigger_condition": "if_opened_no_reply"
        })
        
        if pending_opened:
            # Reschedule existing pending one relative to MAIN SENT TIME
            delay = pending_opened.get("days_delay", 1)
            new_sched = get_next_business_time(sent_at, delay, target_hour=sent_at.hour)
            await db.follow_ups.update_one(
                {"id": pending_opened["id"]},
                {"$set": {"scheduled_at": new_sched.isoformat()}}
            )
            logging.info(f"Rescheduled existing FUP relative to sent_at (pixel) for {original_tid}")
        else:
            # 3. PROACTIVE FETCH: Schedule ONLY THE FIRST 'opened_no_reply' stage
            rules = await db.automation_rules.find({"user_id": em["user_id"]}).to_list(100)
            
            for rule in rules:
                rule_name = rule.get("name", "Unnamed Rule")
                all_stages = rule.get("stages", [])
                open_stages = [s for s in all_stages if s.get("trigger") in ["opened_no_reply", "no_reply"]]
                
                if open_stages:
                    stage = open_stages[0]
                    val = stage.get("delay_value", 1)
                    unit = stage.get("delay_unit", "days")
                    time_val = stage.get("time")
                    hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else sent_at.hour
                    new_sched = get_next_business_time(sent_at, val, unit=unit, target_hour=hour)
                    
                    await _create_fup(original_tid, stage["message"], val, unit, "auto", "if_opened_no_reply", em["user_id"], custom_scheduled_at=new_sched, time=time_val, sequence_order=1)
                    logging.info(f"Proactively scheduled 1st 'opened_no_reply' stage from '{rule_name}' ({val} {unit}) for {original_tid}")

    return Response(content=PIXEL_PNG, media_type="image/png", headers={
        "Cache-Control": "private, no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
        "Pragma": "no-cache", "Expires": "0"
    })

# ---------- Email queries ----------
@api_router.get("/emails")
async def list_emails(user: dict = Depends(get_current_user)):
    rows = await db.tracked_emails.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("sent_at", -1).to_list(500)
    
    tids = [r["id"] for r in rows]
    
    # 1. Map sent counts
    all_sent = await db.follow_ups.aggregate([
        {"$match": {"tracked_email_id": {"$in": tids}, "sent": True}},
        {"$group": {"_id": "$tracked_email_id", "count": {"$sum": 1}}}
    ]).to_list(500)
    sent_map = {s["_id"]: s["count"] for s in all_sent}
    
    # 2. Map next pending follow-up (earliest)
    all_pending = await db.follow_ups.find(
        {"tracked_email_id": {"$in": tids}, "sent": False}
    ).sort("scheduled_at", 1).to_list(1000)
    
    pending_map = {}
    for p in all_pending:
        tid = p["tracked_email_id"]
        if tid not in pending_map:
            pending_map[tid] = p
    for r in rows:
        tid = r["id"]
        sent_count = sent_map.get(tid, 0)
        
        # SELF-HEALING: Find the next valid follow-up
        relevant_p = None
        is_opened = r.get("open_count", 0) > 0
        
        for p in all_pending:
            if p["tracked_email_id"] != tid:
                continue
                
            cond = p.get("trigger_condition", "")
            
            # If opened, 'no open' is invalid
            if is_opened and cond in ["if_no_open", "if_not_opened"]:
                # Proactively delete stale record
                await db.follow_ups.delete_one({"id": p["id"]})
                continue
                
            # If not opened, 'opened but no reply' is valid but 'waiting'
            if cond == "if_opened_no_reply" and not is_opened:
                relevant_p = p
                break
                
            # Otherwise, if it's the right condition, it's our next step
            relevant_p = p
            break
            
        if relevant_p:
            r["next_followup"] = {
                "id": relevant_p["id"],
                "subject": relevant_p["subject"],
                "scheduled_at": relevant_p["scheduled_at"],
                "condition": relevant_p["trigger_condition"],
                "label": relevant_p["message"][:20] + "..." if len(relevant_p["message"]) > 20 else relevant_p["message"]
            }
        elif is_opened:
            # SUPER-PROACTIVE: Scan ALL rules for an 'open' trigger
            rules = await db.automation_rules.find({"user_id": user["user_id"]}).to_list(10)
            found = False
            for rule in rules:
                if found: break
                stage = next((s for s in rule.get("stages", []) if s.get("trigger") in ["opened_no_reply", "no_reply"]), None)
                if stage:
                    trigger = stage.get("trigger", "no_reply")
                    cond = "if_opened_no_reply" if trigger == "opened_no_reply" else "if_no_reply"
                    
                    # Check if it was already sent (to avoid double-creating)
                    already_sent = await db.follow_ups.find_one({"tracked_email_id": tid, "trigger_condition": cond, "sent": True})
                    if not already_sent:
                        val = stage.get("delay_value") or stage.get("days", 1)
                        unit = stage.get("delay_unit", "days")
                        new_sched = get_next_business_time(datetime.now(timezone.utc), val, unit=unit)
                        new_fup = await _create_fup(tid, stage["message"], val, unit, "auto", cond, user["user_id"], custom_scheduled_at=new_sched, sequence_order=1)
                        r["next_followup"] = {
                            "id": new_fup["id"],
                            "subject": new_fup["subject"],
                            "scheduled_at": new_fup["scheduled_at"],
                            "condition": new_fup["trigger_condition"],
                            "label": new_fup["message"][:20] + "..." if len(new_fup["message"]) > 20 else new_fup["message"]
                        }
                        logging.info(f"Dashboard proactively created missing FUP from rule '{rule.get('name')}' for {tid}")
                        found = True
        else:
            r["next_followup"] = None
            
    return rows

@api_router.get("/emails/by-ext")
async def list_emails_ext(user: dict = Depends(get_user_by_ext_key)):
    rows = await db.tracked_emails.find(
        {"user_id": user["user_id"]}, {"_id": 0, "opens": 0}
    ).sort("sent_at", -1).to_list(100)
    return rows

@api_router.get("/stream")
async def sse_stream(request: Request, user: dict = Depends(get_user_by_ext_key)):
    user_id = user["user_id"]
    q = asyncio.Queue()
    queues = event_queues.setdefault(user_id, [])
    queues.append(q)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in queues:
                queues.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@api_router.get("/emails/{eid}")
async def email_detail(eid: str, user: dict = Depends(get_current_user)):
    em = await db.tracked_emails.find_one(
        {"id": eid, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not em:
        raise HTTPException(404, "Not found")
    return em

@api_router.delete("/emails/{eid}")
async def delete_email(eid: str, user: dict = Depends(get_current_user)):
    await db.tracked_emails.delete_one({"id": eid, "user_id": user["user_id"]})
    await db.follow_ups.delete_many({"tracked_email_id": eid, "user_id": user["user_id"]})
    return {"ok": True}

@api_router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    total = await db.tracked_emails.count_documents({"user_id": uid})
    opened = await db.tracked_emails.count_documents({"user_id": uid, "open_count": {"$gt": 0}})
    replied = await db.tracked_emails.count_documents({"user_id": uid, "replied": True})

    # Count pending follow-ups for non-replied emails only (match Pipeline logic)
    pending_agg = await db.follow_ups.aggregate([
        {"$match": {"user_id": uid, "sent": False}},
        {"$lookup": {
            "from": "tracked_emails",
            "localField": "tracked_email_id",
            "foreignField": "id",
            "as": "email"
        }},
        {"$unwind": "$email"},
        {"$match": {"email.replied": {"$ne": True}}},
        {"$count": "count"}
    ]).to_list(1)
    follow_ups_pending = pending_agg[0]["count"] if pending_agg else 0
    
    follow_ups_sent = await db.follow_ups.count_documents({"user_id": uid, "sent": True})
    
    return {
        "total_sent": total,
        "total_opened": opened,
        "total_not_opened": total - opened,
        "total_replied": replied,
        "follow_ups_pending": follow_ups_pending,
        "follow_ups_sent": follow_ups_sent,
    }

# ---------- Follow-ups ----------
@api_router.post("/follow-ups")
async def create_follow_up(payload: FollowUpCreate, user: dict = Depends(get_current_user)):
    return await _create_fup(payload.tracked_email_id, payload.message, payload.days_delay, "days", payload.mode, payload.trigger_condition, user["user_id"], time=None)

class BulkFollowUpCreate(BaseModel):
    tracked_email_ids: List[str]
    message: str
    days_delay: int = 3
    mode: str = "manual"
    trigger_condition: str = "always"

@api_router.post("/follow-ups/bulk")
async def bulk_create_follow_up(payload: BulkFollowUpCreate, user: dict = Depends(get_current_user)):
    results = []
    for eid in payload.tracked_email_ids:
        try:
            res = await _create_fup(eid, payload.message, payload.days_delay, "days", payload.mode, payload.trigger_condition, user["user_id"], time=None)
            results.append(res)
        except Exception:
            continue
    return results

async def stop_sequences(tracked_email_id: str, user_id: str):
    """Stops and deletes all pending follow-ups for a specific email."""
    result = await db.follow_ups.delete_many({
        "tracked_email_id": tracked_email_id,
        "user_id": user_id,
        "sent": False
    })
    logging.info(f"Stopped {result.deleted_count} pending follow-ups for {tracked_email_id}")
    return result.deleted_count

async def _create_fup(eid, message, delay_value, delay_unit, mode, condition, user_id, 
                  custom_scheduled_at=None, time=None, 
                  sequence_order=0, repeated_followup=False, repeated_cycle=0):
    em = await db.tracked_emails.find_one({"id": eid, "user_id": user_id}, {"_id": 0})
    if not em:
        raise HTTPException(404, "Tracked email not found")
    
    # Safety: Don't schedule for already replied emails
    if em.get("replied"):
        logging.warning(f"Aborted FUP creation for {eid}: Already replied.")
        return None

    # DE-DUPLICATION: Don't create if exact same stage already exists (pending or sent)
    # For repeated follow-ups, we allow creation if the cycle is different
    existing = await db.follow_ups.find_one({
        "tracked_email_id": eid,
        "delay_value": delay_value,
        "delay_unit": delay_unit,
        "trigger_condition": condition,
        "repeated_cycle": repeated_cycle,
        "user_id": user_id
    })
    if existing:
        logging.info(f"FUP stage ({delay_value} {delay_unit}, {condition}, Cycle {repeated_cycle}) already exists for {eid}. Skipping.")
        return existing
    
    fid = uuid.uuid4().hex
    if custom_scheduled_at:
        scheduled = custom_scheduled_at
    else:
        sent_at_raw = em.get("sent_at")
        sent_at = datetime.fromisoformat(sent_at_raw) if isinstance(sent_at_raw, str) else sent_at_raw
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        
        if delay_unit == "hours":
            scheduled = sent_at + timedelta(hours=delay_value)
        else:
            scheduled = sent_at + timedelta(days=delay_value)

    doc = {
        "id": fid,
        "user_id": user_id,
        "tracked_email_id": eid,
        "recipient": em["recipient"],
        "subject": em["subject"],
        "message": message,
        "delay_value": delay_value,
        "delay_unit": delay_unit,
        "sequence_order": sequence_order,
        "scheduled_at": scheduled.isoformat(),
        "mode": mode,
        "trigger_condition": condition,
        "time": time,
        "sent": False,
        "completed": False,
        "sent_at": None,
        "status": "scheduled",
        "repeated_followup": repeated_followup,
        "repeated_cycle": repeated_cycle
    }
    await db.follow_ups.insert_one(doc)
    
    # Update current pointer in parent email
    await db.tracked_emails.update_one({"id": eid}, {"$set": {"current_active_followup_id": fid}})

    # Store specific scheduled timestamps in parent email for easier access
    if delay_value == 1 and delay_unit == "days" and not repeated_followup:
        await db.tracked_emails.update_one({"id": eid}, {"$set": {"followup1_scheduled_at": scheduled.isoformat()}})
    elif delay_value == 3 and delay_unit == "days" and not repeated_followup:
        await db.tracked_emails.update_one({"id": eid}, {"$set": {"followup2_scheduled_at": scheduled.isoformat()}})

    doc.pop("_id", None)
    return doc

async def schedule_next_stage(tid, user_id, last_fup):
    """Calculates and schedules the NEXT stage in the automation sequence.
    If no next stage exists, optionally repeats the last one."""
    last_val = last_fup.get("delay_value")
    last_unit = last_fup.get("delay_unit", "days")
    last_cond = last_fup.get("trigger_condition")
    last_order = last_fup.get("sequence_order", 0)
    
    rules = await db.automation_rules.find({"user_id": user_id}).to_list(100)
    if not rules: return
    
    for rule in rules:
        stages = rule.get("stages", [])
        repeat_enabled = rule.get("repeat_last", False)
        
        # Find if this rule contains the stage we just finished
        current_idx = -1
        for i, s in enumerate(stages):
            trigger = s.get("trigger")
            cond = "if_no_open" if trigger == "no_open" else ("if_opened_no_reply" if trigger == "opened_no_reply" else f"if_{trigger}")
            if s.get("delay_value") == last_val and s.get("delay_unit", "days") == last_unit and cond == last_cond:
                current_idx = i
                break
        
        if current_idx != -1:
            next_stage = None
            new_order = last_order + 1
            is_repeated = False
            cycle = 0
            
            if current_idx + 1 < len(stages):
                # NEXT QUEUED FOLLOW-UP EXISTS
                next_stage = stages[current_idx + 1]
                logging.info(f"FOLLOW-UP COMPLETED: Stage {last_order} for {tid}. NEXT STAGE ACTIVATED.")
            elif repeat_enabled:
                # NO MORE STEPS -> TRIGGER REPEAT MODE
                next_stage = stages[current_idx]
                is_repeated = True
                cycle = last_fup.get("repeated_cycle", 0) + 1
                logging.info(f"QUEUE EMPTY for {tid}. REPEATING STAGE (Cycle {cycle}).")
            
            if next_stage:
                now_dt = datetime.now(timezone.utc)
                val = next_stage.get("delay_value", 1)
                unit = next_stage.get("delay_unit", "days")
                
                time_val = next_stage.get("time")
                hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else None
                new_sched = get_next_business_time(now_dt, val, unit=unit, target_hour=hour)
                
                trigger = next_stage.get("trigger")
                cond = "if_no_open" if trigger == "no_open" else ("if_opened_no_reply" if trigger == "opened_no_reply" else f"if_{trigger}")
                
                await _create_fup(
                    tid, next_stage["message"], val, unit, "auto", cond, user_id, 
                    custom_scheduled_at=new_sched, time=time_val, 
                    sequence_order=new_order, repeated_followup=is_repeated, repeated_cycle=cycle
                )
                break

async def find_thread_info(access_token, recipient, subject):
    """Searches Gmail for a thread by recipient and subject to enable correct threading."""
    async with httpx.AsyncClient() as client:
        query = f'to:{recipient} subject:"{subject}"'
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={query}&maxResults=1"
        headers = {"Authorization": f"Bearer {access_token}"}
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            msgs = r.json().get("messages", [])
            if msgs:
                msg_id = msgs[0]["id"]
                # Get full message to find threadId and Message-ID
                r2 = await client.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}", headers=headers)
                if r2.status_code == 200:
                    data = r2.json()
                    thread_id = data.get("threadId")
                    headers_list = data.get("payload", {}).get("headers", [])
                    msg_id_header = next((h["value"] for h in headers_list if h["name"].lower() == "message-id"), None)
                    return thread_id, msg_id_header
    return None, None

async def send_gmail_message(access_token, recipient, subject, body_html, thread_id=None, parent_msg_id=None):
    """Sends an email via Gmail API with support for threading (replies)."""
    from email.mime.text import MIMEText
    import base64

    message = MIMEText(body_html, "html")
    message["to"] = recipient
    message["subject"] = subject
    if thread_id and parent_msg_id:
        message["In-Reply-To"] = parent_msg_id
        message["References"] = parent_msg_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    async with httpx.AsyncClient() as client:
        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        r = await client.post(url, headers=headers, json=payload)
        return r.status_code == 200

# ---------- Automation Rules ----------
@api_router.post("/automation-rules")
async def create_rule(payload: AutomationRuleCreate, user: dict = Depends(get_current_user)):
    rid = uuid.uuid4().hex
    doc = {
        "id": rid,
        "user_id": user["user_id"],
        "name": payload.name,
        "stages": [s.model_dump() for s in payload.stages],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.automation_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/automation-rules")
async def list_rules(user: dict = Depends(get_current_user)):
    return await db.automation_rules.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)

@api_router.get("/follow-ups")
async def list_follow_ups(user: dict = Depends(get_current_user)):
    fups = await db.follow_ups.find({"user_id": user["user_id"]}, {"_id": 0}).sort("scheduled_at", -1).to_list(1000)
    
    # Enrich with latest data from tracked_emails to fix draft/pending labels in UI
    tids = list(set(f["tracked_email_id"] for f in fups))
    emails = await db.tracked_emails.find({"id": {"$in": tids}, "replied": {"$ne": True}}, {"_id": 0, "id": 1, "recipient": 1, "subject": 1, "open_count": 1, "replied": 1}).to_list(len(tids))
    email_map = {e["id"]: e for e in emails}
    
    final_fups = []
    for f in fups:
        em = email_map.get(f["tracked_email_id"])
        if em:
            # --- SELF-HEALING: Delete stale "No Open" follow-ups if email is already opened ---
            is_opened = em.get("open_count", 0) > 0
            is_no_open_fup = f.get("trigger_condition") in ["if_no_open", "if_not_opened"]
            
            if is_opened and is_no_open_fup and not f.get("sent"):
                # This is a stale follow-up. Delete it from DB and skip from list.
                await db.follow_ups.delete_one({"tracked_email_id": em["id"], "trigger_condition": f["trigger_condition"], "sent": False})
                logging.info(f"Self-healed: Deleted stale 'no open' FUP for {em['id']}")
                continue

            # Enrich metadata
            if "unknown" in f.get("recipient", "").lower() and "unknown" not in em.get("recipient", "").lower():
                f["recipient"] = em["recipient"]
            if f.get("subject") == "(draft)" and em.get("subject") != "(draft)":
                f["subject"] = em["subject"]
        
            final_fups.append(f)
                
    return final_fups

@api_router.put("/automation-rules/{rid}")
async def update_rule(rid: str, payload: AutomationRuleCreate, user: dict = Depends(get_current_user)):
    res = await db.automation_rules.update_one(
        {"id": rid, "user_id": user["user_id"]},
        {"$set": {
            "name": payload.name,
            "stages": [s.model_dump() for s in payload.stages],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}

@api_router.delete("/automation-rules/{rid}")
async def delete_rule(rid: str, user: dict = Depends(get_current_user)):
    await db.automation_rules.delete_one({"id": rid, "user_id": user["user_id"]})
    return {"ok": True}


@api_router.get("/follow-ups/due")
async def due_follow_ups(user: dict = Depends(get_user_by_ext_key)):
    """Extension polls for due follow-ups whose tracked email meets the trigger conditions."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 1. Get all unsent follow-ups that are scheduled for now or in the past
    potential_dues = await db.follow_ups.find({
        "user_id": user["user_id"],
        "sent": False,
        "scheduled_at": {"$lte": now_iso},
    }, {"_id": 0}).to_list(100)
    
    if not potential_dues:
        return []
        
    # 2. Filter them based on the actual status of the parent tracked email
    results = []
    for f in potential_dues:
        em = await db.tracked_emails.find_one({"id": f["tracked_email_id"]}, {"_id": 0})
        if not em:
            continue
            
        condition = f.get("trigger_condition", "always")
        
        # Cascade dependency: determine if the *previous* email in the chain was opened.
        # If this is the 1st follow-up, the previous is the main email.
        # If this is the 2nd or later follow-up, the previous is the most recently sent follow-up.
        sent_fups = await db.follow_ups.find({
            "tracked_email_id": f["tracked_email_id"],
            "sent": True
        }).sort("sent_at", -1).to_list(1)
        
        if sent_fups:
            is_opened = sent_fups[0].get("open_count", 0) > 0
        else:
            is_opened = em.get("open_count", 0) > 0

        is_replied = em.get("replied", False)
        
        should_send = False
        if condition == "always":
            should_send = True
        elif condition == "if_not_opened":
            should_send = not is_opened
        elif condition == "if_not_replied":
            should_send = not is_replied
        elif condition == "if_opened_no_reply":
            should_send = is_opened and not is_replied
            
        # Optimization: If the mail is already replied to, we should probably cancel 
        # all future follow-ups anyway, but mark-replied endpoint already does that.
        # This is an extra safety check.
        if is_replied:
            should_send = False
            
        if should_send:
            # Include email status for the extension/dashboard to show
            f["email_status"] = {"opened": is_opened, "replied": is_replied}
            results.append(f)
            
    return results

@api_router.post("/follow-ups/{fid}/mark-sent")
async def mark_sent(fid: str, user: dict = Depends(get_current_user)):
    res = await db.follow_ups.update_one(
        {"id": fid, "user_id": user["user_id"]},
        {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    
    # Increment follow_up_count on parent email
    fup = await db.follow_ups.find_one({"id": fid})
    if fup:
        await db.tracked_emails.update_one(
            {"id": fup["tracked_email_id"]},
            {"$inc": {"follow_up_count": 1}}
        )
        await _schedule_next_stage_if_needed(fup["tracked_email_id"], user["user_id"])
    return {"ok": True}

@api_router.post("/follow-ups/{fid}/mark-sent-ext")
async def mark_sent_ext(fid: str, user: dict = Depends(get_user_by_ext_key)):
    await db.follow_ups.update_one(
        {"id": fid, "user_id": user["user_id"]},
        {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Increment follow_up_count on parent email
    fup = await db.follow_ups.find_one({"id": fid})
    if fup:
        await db.tracked_emails.update_one(
            {"id": fup["tracked_email_id"]},
            {"$inc": {"follow_up_count": 1}}
        )
        await _schedule_next_stage_if_needed(fup["tracked_email_id"], user["user_id"])
    return {"ok": True}

async def _schedule_next_stage_if_needed(tid: str, user_id: str):
    em = await db.tracked_emails.find_one({"id": tid, "user_id": user_id})
    if not em or em.get("replied"):
        return

    # Count how many follow-ups have been sent
    sent_count = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": True})
    
    # Are there any pending ones?
    pending_count = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": False})
    if pending_count > 0:
        return

    rules = await db.automation_rules.find({"user_id": user_id}).sort([("updated_at", -1), ("created_at", -1)]).to_list(1)
    all_stages = rules[0].get("stages", []) if rules else []
    
    if not all_stages:
        return
    
    # Dual-branch logic: choose relevant stages based on open status
    is_opened = em.get("open_count", 0) > 0
    if is_opened:
        relevant_stages = [s for s in all_stages if s.get("trigger") in ["opened_no_reply", "no_reply"]]
        default_cond = "if_opened_no_reply"
    else:
        relevant_stages = [s for s in all_stages if s.get("trigger") in ["no_open"]]
        default_cond = "if_no_open"
        
    if sent_count < len(relevant_stages):
        next_stage = relevant_stages[sent_count]
        trigger = next_stage.get("trigger")
        
        if trigger == "no_open": cond = "if_no_open"
        elif trigger == "opened_no_reply": cond = "if_opened_no_reply"
        else: cond = default_cond
        
        now_dt = datetime.now(timezone.utc)
        delay = next_stage.get("days", 1)
        time_val = next_stage.get("time")
        
        # Calculate schedule relative to MAIN email sent time for consistency
        sent_at_raw = em.get("sent_at")
        sent_at = datetime.fromisoformat(sent_at_raw) if isinstance(sent_at_raw, str) else sent_at_raw
        if sent_at and sent_at.tzinfo is None: sent_at = sent_at.replace(tzinfo=timezone.utc)
        
        hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else sent_at.hour
        new_sched = get_next_business_time(sent_at, delay, target_hour=hour)
        
        # If new_sched is in the past (because we are late), schedule for soon
        if new_sched < now_dt:
            new_sched = now_dt + timedelta(minutes=5)

        await _create_fup(
            tid, 
            next_stage["message"], 
            delay, 
            "days",
            "auto", 
            cond, 
            user_id, 
            custom_scheduled_at=new_sched, 
            time=time_val
        )
        logging.info(f"Scheduled next stage ({cond}, Day {delay}) for {tid}")


@api_router.post("/emails/{tid}/sequence")
async def start_sequence(tid: str, user: dict = Depends(get_current_user)):
    """Schedules a sequence of 3 follow-ups on Day 1, Day 3, and Day 5 (business days only)."""
    em = await db.tracked_emails.find_one({"id": tid, "user_id": user["user_id"]})
    if not em:
        raise HTTPException(404, "Email not found")
        
    # Check if already has follow-ups to avoid duplicates
    existing = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": False})
    if existing > 0:
        raise HTTPException(400, "Sequence or follow-up already active for this email")

    # Sequence configuration
    # 1st FUP: 24h later (Day 1)
    # 2nd FUP: Day 3
    # 3rd FUP: Day 5
    steps = [
        {"days": 1, "msg": "Hi, just checking if you saw my previous email?"},
        {"days": 3, "msg": "Wanted to follow up on this and see if you had any questions?"},
        {"days": 5, "msg": "Final check-in regarding this thread. Let me know if you're interested."}
    ]
    
    sent_at = datetime.fromisoformat(em["sent_at"].replace("Z", "+00:00"))
    
    created_count = 0
    for step in steps:
        scheduled_at = get_next_business_time(sent_at, step["days"])
        fup_id = secrets.token_hex(8)
        
        fup = {
            "id": fup_id,
            "user_id": user["user_id"],
            "tracked_email_id": tid,
            "recipient": em["recipient"],
            "subject": f"Re: {em['subject']}",
            "message": step["msg"],
            "days_delay": step["days"],
            "scheduled_at": scheduled_at.isoformat(),
            "mode": "auto",
            "sent": False,
            "trigger_condition": "if_not_replied"
        }
        await db.follow_ups.insert_one(fup)
        created_count += 1
        
    return {"ok": True, "count": created_count}

@api_router.delete("/follow-ups/{fid}")
async def delete_follow_up(fid: str, user: dict = Depends(get_current_user)):
    await db.follow_ups.delete_one({"id": fid, "user_id": user["user_id"]})
    return {"ok": True}

@api_router.post("/emails/{tid}/test-followup")
async def test_followup(tid: str, user: dict = Depends(get_current_user)):
    """TEST ENDPOINT: Immediately sends a follow-up via Gmail API for testing."""
    em = await db.tracked_emails.find_one({"id": tid, "user_id": user["user_id"]})
    if not em:
        raise HTTPException(404, "Email not found")
        
    rule = await db.automation_rules.find_one({"user_id": user["user_id"]})
    if not rule or not rule.get("stages"):
        raise HTTPException(400, "No automation rules found. Please create one on the Automation page first.")
        
    stage = rule["stages"][0]
    msg_text = stage["message"]
    
    if not user.get("access_token"):
        raise HTTPException(400, "Gmail access not found. Please log out and log in again to grant permission.")

    # Generate pixel for tracking the test follow-up too
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
    fup_id = secrets.token_hex(8)
    pixel_url = f"{backend_url}/api/track/pixel/{fup_id}.png"
    pixel_html = f'<img src="{pixel_url}" width="1" height="1" style="display:none;" />'
    full_body = f"{msg_text}<br/><br/>{pixel_html}"
    
    # Try to find the original thread info to reply in the same thread
    thread_id, parent_msg_id = await find_thread_info(user["access_token"], em["recipient"], em["subject"])
    
    success = await send_gmail_message(
        user["access_token"], 
        em["recipient"], 
        f"Re: {em['subject']}", 
        full_body,
        thread_id=thread_id,
        parent_msg_id=parent_msg_id
    )
    
    if success:
        # Record it as a sent follow-up in the history
        await db.follow_ups.insert_one({
            "id": fup_id,
            "user_id": user["user_id"],
            "tracked_email_id": tid,
            "recipient": em["recipient"],
            "subject": f"Re: {em['subject']}",
            "message": msg_text,
            "days_delay": 0,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "mode": "auto",
            "sent": True,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "trigger_condition": "test"
        })
        
        await db.tracked_emails.update_one({"id": tid}, {"$inc": {"follow_up_count": 1}})
        return {"ok": True, "message": "Test follow-up sent successfully via Gmail API"}
    else:
        # If we reached here, the Gmail send failed.
        raise HTTPException(status_code=401, detail="GMAIL_TOKEN_EXPIRED")

# ---------- Gmail API Integration ----------
async def ensure_google_token(user_id: str):
    """Retrieves a valid access token for the user, refreshing it if necessary."""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return None
        
    access_token = user.get("access_token")
    refresh_token = user.get("refresh_token")
    
    if not refresh_token:
        # If no refresh token, we just have to hope the access token is still valid
        return access_token

    # Check local cache for valid token status to avoid redundant Google API hits
    now = time.time()
    cache_key = f"token_valid_{user_id}"
    if AUTH_CACHE.get(cache_key, 0) > now:
        return access_token

    # Check if the current token works
    async with httpx.AsyncClient() as client:
        test_res = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo", 
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if test_res.status_code == 200:
            # Cache the validity for 30 minutes
            AUTH_CACHE[cache_key] = now + 1800
            return access_token
            
        # If 401, refresh the token
        logging.info(f"Refreshing Google token for {user_id}...")
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        
        refresh_res = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        })
        
        if refresh_res.status_code == 200:
            new_data = refresh_res.json()
            new_access_token = new_data.get("access_token")
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"access_token": new_access_token}}
            )
            return new_access_token
        else:
            logging.error(f"Failed to refresh token for {user_id}: {refresh_res.text}")
            return None

async def find_thread_info(access_token: str, recipient: str, subject: str):
    """Searches for the threadId and Message-ID of the original sent email."""
    # We search in 'sent' for messages to the recipient with the specific subject
    # We use a slightly looser search to ensure we find it
    query = f'to:{recipient} subject:"{subject}"'
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={query}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code == 200:
            data = r.json()
            if data.get("messages"):
                # Get the most recent matching message
                msg_summary = data["messages"][0]
                tid = msg_summary.get("threadId")
                mid = msg_summary.get("id")
                
                # We need the actual 'Message-ID' header for threading
                detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}"
                dr = await client.get(detail_url, headers={"Authorization": f"Bearer {access_token}"})
                if dr.status_code == 200:
                    ddata = dr.json()
                    headers = ddata.get("payload", {}).get("headers", [])
                    msg_id_header = next((h["value"] for h in headers if h["name"].lower() == "message-id"), None)
                    return tid, msg_id_header
    return None, None

async def send_gmail_message(access_token: str, recipient: str, subject: str, body_html: str, thread_id: str = None, parent_msg_id: str = None):
    """Sends an email using the Gmail API as a threaded reply."""
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    
    from email.mime.text import MIMEText
    message = MIMEText(body_html, "html")
    message["to"] = recipient
    message["subject"] = subject
    
    if parent_msg_id:
        # Crucial for grouping in most email clients
        message["In-Reply-To"] = parent_msg_id
        message["References"] = parent_msg_id
    
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload
        )
        return r.status_code == 200

async def process_reply_check_task(task):
    payload = task["payload"]
    tracked_id = payload.get("tracked_id")
    user_id = task["user_id"]
    
    em = await db.tracked_emails.find_one({"id": tracked_id})
    if not em or em.get("replied"): return True
    
    token = await ensure_google_token(user_id)
    if not token: return False
    
    user = await db.users.find_one({"user_id": user_id})
    my_email = user.get("email", "").lower() if user else ""
    
    if em.get("gmail_thread_id"):
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                thread_url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{em['gmail_thread_id']}"
                r = await client.get(thread_url, headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    msgs = r.json().get("messages", [])
                    for m in msgs:
                        hds = m.get("payload", {}).get("headers", [])
                        frm = next((h["value"].lower() for h in hds if h["name"].lower() == "from"), "")
                        if frm and my_email and my_email not in frm:
                            await db.tracked_emails.update_one({"id": em["id"]}, {"$set": {"replied": True, "last_activity_at": datetime.now(timezone.utc).isoformat()}})
                            await stop_sequences(em["id"], user_id)
                            logging.info(f"Reply detected for {em['id']} via autonomous task.")
                            return True
            except Exception: pass
    return True

async def reply_watcher_dispatcher():
    """Periodically queues reply check tasks for all active follow-up sequences."""
    while True:
        try:
            # Find all tracked emails that have active (scheduled) follow-ups and haven't been checked in 30 mins
            active_tracked = await db.tracked_emails.find({
                "replied": {"$ne": True}
            }).to_list(100)
            
            for em in active_tracked:
                # Only check if there are pending follow-ups
                has_pending = await db.follow_ups.count_documents({"tracked_email_id": em["id"], "sent": False, "status": "scheduled"})
                if has_pending > 0:
                    await schedule_task(em["user_id"], "check_replies", {"tracked_id": em["id"]}, datetime.now(timezone.utc))
        except Exception as e:
            logging.error(f"Error in reply_watcher_dispatcher: {e}")
        await asyncio.sleep(1800) # Every 30 minutes



            
async def schedule_task(user_id: str, task_type: str, payload: dict, scheduled_at: datetime):
    tid = uuid.uuid4().hex
    task = {
        "id": tid,
        "user_id": user_id,
        "type": task_type,
        "payload": payload,
        "status": "pending",
        "scheduled_at": scheduled_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retries": 0,
        "max_retries": 3,
        "error_log": []
    }
    await db.tasks.insert_one(task)
    logging.info(f"TASK QUEUED: {task_type} for {user_id} at {scheduled_at.isoformat()}")
    return tid

async def task_worker():
    """Persistent background worker that processes the task queue with retry logic."""
    logging.info("Autonomous Task Worker started.")
    while True:
        try:
            now = datetime.now(timezone.utc).isoformat()
            # Find one pending task that is due
            task = await db.tasks.find_one_and_update(
                {
                    "status": {"$in": ["pending", "retrying"]},
                    "scheduled_at": {"$lte": now}
                },
                {"$set": {"status": "running", "started_at": now}},
                sort=[("scheduled_at", 1)]
            )
            
            if not task:
                await asyncio.sleep(10)
                continue
                
            logging.info(f"PROCESSING TASK: {task['type']} ({task['id']})")
            success = False
            error_msg = ""
            
            try:
                if task["type"] == "send_fup":
                    success = await process_send_task(task)
                elif task["type"] == "check_replies":
                    success = await process_reply_check_task(task)
                # ... add other task types ...
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Task {task['id']} failed: {e}")
            
            if success:
                await db.tasks.update_one({"id": task["id"]}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}})
            else:
                retries = task.get("retries", 0) + 1
                if retries <= task.get("max_retries", 3):
                    # Exponential backoff: 5m, 15m, 45m...
                    delay = (3 ** retries) * 300 
                    next_run = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    await db.tasks.update_one(
                        {"id": task["id"]}, 
                        {
                            "$set": {"status": "retrying", "retries": retries, "scheduled_at": next_run.isoformat()},
                            "$push": {"error_log": f"Attempt {retries} failed: {error_msg}"}
                        }
                    )
                else:
                    await db.tasks.update_one(
                        {"id": task["id"]}, 
                        {"$set": {"status": "failed", "failed_at": datetime.now(timezone.utc).isoformat()}}
                    )
                    logging.error(f"TASK PERMANENTLY FAILED: {task['id']}")
                    
        except Exception as e:
            logging.error(f"Critical error in task_worker: {e}")
            await asyncio.sleep(30)

async def process_send_task(task):
    payload = task["payload"]
    fup_id = payload.get("fup_id")
    f = await db.follow_ups.find_one({"id": fup_id})
    if not f or f.get("sent") or f.get("status") == "stopped":
        return True # Task no longer relevant
    
    # Reuse existing send logic but adapted for task worker
    # I'll call a helper function here
    return await execute_fup_send(f)

async def execute_fup_send(f):
    # Logic extracted from the old automation_worker
    token = await ensure_google_token(f["user_id"])
    if not token: return False
    
    em = await db.tracked_emails.find_one({"id": f["tracked_email_id"]})
    if not em or em.get("replied"): return True
    
    # 3. Inject tracking pixel
    thread_id, parent_msg_id = await find_thread_info(token, em["recipient"], em["subject"])
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
    pixel_url = f"{backend_url}/api/track/pixel/{f['id']}.png"
    pixel_html = f'<img src="{pixel_url}" width="1" height="1" style="display:none;" />'
    full_body = f"{f['message']}<br/><br/>{pixel_html}"
    
    success = await send_gmail_message(
        token, 
        em["recipient"], 
        em["subject"], 
        full_body,
        thread_id=thread_id,
        parent_msg_id=parent_msg_id
    )
    if success:
        now_sent = datetime.now(timezone.utc).isoformat()
        await db.follow_ups.update_one(
            {"id": f["id"]},
            {"$set": {"sent": True, "completed": True, "sent_at": now_sent, "status": "sent"}}
        )
        # Update tracked_emails with specific timestamps for FUP1, FUP2 (UI compatibility)
        upd = {"$inc": {"follow_up_count": 1}, "$set": {"last_activity_at": now_sent}}
        val = f.get("delay_value", 1)
        unit = f.get("delay_unit", "days")
        if val == 1 and unit == "days":
            upd["$set"]["followup1_sent_at"] = now_sent
        elif val == 3 and unit == "days":
            upd["$set"]["followup2_sent_at"] = now_sent
            
        await db.tracked_emails.update_one({"id": em["id"]}, upd)
        push_event(f["user_id"], {"type": "followup_sent", "tracked_id": em["id"]})
        await schedule_next_stage(em["id"], f["user_id"], f)
        return True
    return False

@app.on_event("startup")
async def startup_event():
    # 1. RECOVERY: Reset any 'running' tasks from previous crash
    await db.tasks.update_many({"status": "running"}, {"$set": {"status": "pending"}})
    
    # 2. START WORKERS
    asyncio.create_task(task_worker())
    
    # 3. DISPATCHER: Periodically convert scheduled FUPs into tasks
    asyncio.create_task(dispatcher_worker())
    
    # 4. REPLY WATCHER: Periodically check threads for replies
    asyncio.create_task(reply_watcher_dispatcher())

async def dispatcher_worker():
    """Periodically scans the follow_ups collection and moves due items into the task queue."""
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            # Find follow-ups that are due but don't have a task yet
            dues = await db.follow_ups.find({
                "sent": False,
                "status": "scheduled",
                "scheduled_at": {"$lte": now_iso},
                "task_queued": {"$ne": True}
            }).to_list(50)
            
            for f in dues:
                await schedule_task(f["user_id"], "send_fup", {"fup_id": f["id"]}, datetime.fromisoformat(f["scheduled_at"]))
                await db.follow_ups.update_one({"id": f["id"]}, {"$set": {"task_queued": True}})
                
        except Exception as e:
            logging.error(f"Error in dispatcher_worker: {e}")
        await asyncio.sleep(60)

# ---------- SSE notifications ----------
@api_router.get("/events/stream")
async def events_stream(request: Request):
    # Allow token via query for EventSource
    token = request.query_params.get("token")
    key = request.query_params.get("key")
    user = None
    if token:
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    elif key:
        user = await db.users.find_one({"ext_api_key": key}, {"_id": 0})
        
    if not user:
        try:
            # Pass None for the authorization header if calling manually
            user = await get_current_user(request, authorization=None)
        except HTTPException:
            raise HTTPException(401, "Not authenticated")

    uid = user["user_id"]
    queue: asyncio.Queue = asyncio.Queue()
    event_queues.setdefault(uid, []).append(queue)

    async def gen():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            try:
                event_queues[uid].remove(queue)
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Credentials": "true"
    })

# ---------- root ----------
@api_router.get("/")
async def root():
    return {"message": "MailTrack API"}



class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Identify client (use user_id if logged in, else IP)
        client_id = "unknown"
        if request.client:
            client_id = request.client.host
        
        # Apply different limits based on path
        path = request.url.path
        if path.startswith("/api/track"):
            if not track_limiter.is_allowed(client_id):
                return Response(content='{"error": "Too many tracking hits"}', status_code=429, media_type="application/json")
        elif path.startswith("/api"):
            if not api_limiter.is_allowed(client_id):
                return Response(content='{"error": "Too many requests. Please wait."}', status_code=429, media_type="application/json")
        
        response = await call_next(request)
        if response.status_code == 422:
            logging.error(f"422 Error at {path}")
        return response

app.add_middleware(RateLimitMiddleware)

@api_router.get("/download/source")
async def download_source():
    from fastapi.responses import FileResponse
    path = ROOT_DIR / "mailtrack-source.zip"
    if not path.exists():
        raise HTTPException(404, "Source not built")
    return FileResponse(
        str(path),
        media_type="application/zip",
        filename="mailtrack-source.zip",
        headers={"Content-Disposition": 'attachment; filename="mailtrack-source.zip"'},
    )

@api_router.get("/download/extension")
async def download_extension():
    from fastapi.responses import FileResponse
    # Built zip lives in frontend/public (created by build step)
    path = Path("/app/frontend/public/extension.zip")
    if not path.exists():
        raise HTTPException(404, "Extension not built")
    return FileResponse(
        str(path),
        media_type="application/zip",
        filename="mailtrack-extension.zip",
        headers={"Content-Disposition": 'attachment; filename="mailtrack-extension.zip"'},
    )

# Single source of truth for CORS (Consolidated at the top)
# Router inclusion
app.include_router(api_router, prefix="/api")




logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

# Force uvicorn reload to pick up .env changes
