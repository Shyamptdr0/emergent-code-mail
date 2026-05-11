from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, Response as FastResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import json
import uuid
import secrets
import base64
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import httpx

def get_next_business_time(dt: datetime, days_offset: int, target_hour: int = 10):
    """Calculates the next scheduled time, skipping weekends and moving to Monday 10AM."""
    target = dt + timedelta(days=days_offset)
    # If the target falls on a weekend, or if it's sent on Friday and 24h later is Saturday
    # The user says: "Friday ko kiya to saturday/sunday ko nhi jayega direct monday 10 baje"
    
    # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    if target.weekday() >= 5: # Saturday or Sunday
        days_to_monday = (7 - target.weekday()) % 7
        target = target + timedelta(days=days_to_monday)
        target = target.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    
    return target
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()

async def get_user_by_ext_key(request: Request) -> dict:
    x_ext_key = request.headers.get("X-Ext-Key") or request.query_params.get("key")
    if not x_ext_key:
        raise HTTPException(status_code=401, detail="Missing extension key")
    user = await db.users.find_one({"ext_api_key": x_ext_key}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid extension key")
    return user

api_router = APIRouter(prefix="/api")

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
    days_delay: int
    scheduled_at: str
    mode: str
    sent: bool = False
    sent_at: Optional[str] = None
    trigger_condition: str = "always"
    open_count: int = 0
    opens: List[Dict[str, Any]] = []

class AutomationStage(BaseModel):
    trigger: str
    days: int
    time: str # 'HH:MM'
    message: str

class AutomationRuleCreate(BaseModel):
    name: str
    stages: List[AutomationStage]

class AutomationRule(BaseModel):
    id: str
    user_id: str
    name: str
    stages: List[AutomationStage]
    created_at: str

# ---------- Auth helpers ----------
async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    token = request.cookies.get("session_token")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
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
    email = payload.get("email")
    name = payload.get("name") or email
    picture = payload.get("picture")
    access_token = payload.get("access_token")

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        ext_api_key = existing.get("ext_api_key") or secrets.token_urlsafe(24)
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": name, 
                "picture": picture, 
                "ext_api_key": ext_api_key,
                "access_token": access_token
            }},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        ext_api_key = secrets.token_urlsafe(24)
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "ext_api_key": ext_api_key,
            "access_token": access_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    response.set_cookie(
        "session_token", session_token,
        httponly=True, secure=True, samesite="none",
        max_age=7 * 24 * 60 * 60, path="/",
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
async def update_tracked(tid: str, payload: TrackUpdate, user: dict = Depends(get_user_by_ext_key)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["status"] = "sent"
    updates["sent_at"] = datetime.now(timezone.utc).isoformat()
    if updates:
        await db.tracked_emails.update_one(
            {"id": tid, "user_id": user["user_id"]},
            {"$set": updates},
        )
        
        # Apply Automation Sequences
        # Avoid duplicate scheduling if follow-ups already exist for this TID
        existing_scheduled = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": False})
        if existing_scheduled > 0:
            return {"ok": True}

        rules = await db.automation_rules.find({"user_id": user["user_id"]}).to_list(100)
        sent_at = datetime.now(timezone.utc)
        
        # Check if any follow-ups were already sent (e.g. manual or test)
        # to skip those stages in the sequence
        sent_count = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": True})

        for rule in rules:
            for idx, stage in enumerate(rule["stages"]):
                if idx < sent_count:
                    continue # Skip stages that have already been fulfilled
                
                # Calculate scheduled time using the weekend-aware logic
                scheduled = get_next_business_time(sent_at, stage["days"], target_hour=int(stage["time"].split(":")[0]))
                
                await _create_fup(
                    tid, 
                    stage["message"], 
                    stage["days"], 
                    "auto", 
                    f"if_{stage['trigger']}", 
                    user["user_id"],
                    custom_scheduled_at=scheduled
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
    # Cancel pending follow-ups
    await db.follow_ups.delete_many({
        "tracked_email_id": tid,
        "user_id": user["user_id"],
        "sent": False
    })
    return {"ok": True, "verified": True}

@api_router.get("/emails/active")
async def list_active_mails(user: dict = Depends(get_current_user)):
    """Return only emails that have been replied to."""
    return await db.tracked_emails.find({"user_id": user["user_id"], "replied": True}, {"_id": 0}).to_list(100)

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

from pydantic import BaseModel
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
            "$set": {"last_opened_at": ts},
            "$push": {"opens": {"ts": ts, "ua": ua, "ip": ip}},
        }
    )
    
    # Notify ONLY if we haven't notified in the last 10 seconds (Deduplication)
    last_notified = em.get("last_notified_at")
    should_notify = True
    if last_notified:
        ln_dt = datetime.fromisoformat(last_notified)
        if (now - ln_dt.replace(tzinfo=timezone.utc)).total_seconds() < 10:
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
    return {"ok": True}

@api_router.get("/emails")
async def list_emails(user: dict = Depends(get_current_user)):
    return await db.tracked_emails.find({"user_id": user["user_id"]}, {"_id": 0}).sort("sent_at", -1).to_list(100)

@api_router.get("/emails/by-ext")
async def list_emails_by_ext(user: dict = Depends(get_user_by_ext_key)):
    return await db.tracked_emails.find({"user_id": user["user_id"]}, {"_id": 0}).sort("sent_at", -1).to_list(100)

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
        return FastResponse(content=PIXEL_PNG, media_type="image/png")

    # Ignore draft loads
    if em.get("status") == "draft":
        return FastResponse(content=PIXEL_PNG, media_type="image/png")

    # Wait for extension to ping /mark-viewing
    await asyncio.sleep(2.0)
    
    # Re-fetch for updated self-viewing flags
    em = await db.tracked_emails.find_one({"id": original_tid})
    if not em: return FastResponse(content=PIXEL_PNG, media_type="image/png")

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

    is_scan = (
        seconds_since_send < 2 
        or is_self_viewing 
        or (em.get("sender_ip") and ip == em.get("sender_ip")) # IP-based self-view protection
        or (is_google_scanner_ip and not is_image_proxy)
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
            "$set": {"last_opened_at": ts},
            "$push": {"opens": {"ts": ts, "ua": ua, "ip": ip}}
        })
        # Push notification ONLY if not recently notified
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

    return FastResponse(content=PIXEL_PNG, media_type="image/png", headers={
        "Cache-Control": "private, no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
        "Pragma": "no-cache", "Expires": "0"
    })

# ---------- Email queries ----------
@api_router.get("/emails")
async def list_emails(user: dict = Depends(get_current_user)):
    rows = await db.tracked_emails.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("sent_at", -1).to_list(500)
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
    follow_ups_pending = await db.follow_ups.count_documents({"user_id": uid, "sent": False})
    follow_ups_sent = await db.follow_ups.count_documents({"user_id": uid, "sent": True})
    open_rate = round((opened / total) * 100, 1) if total else 0.0
    return {
        "total_sent": total,
        "total_opened": opened,
        "open_rate": open_rate,
        "follow_ups_pending": follow_ups_pending,
        "follow_ups_sent": follow_ups_sent,
    }

# ---------- Follow-ups ----------
@api_router.post("/follow-ups")
async def create_follow_up(payload: FollowUpCreate, user: dict = Depends(get_current_user)):
    return await _create_fup(payload.tracked_email_id, payload.message, payload.days_delay, payload.mode, payload.trigger_condition, user["user_id"])

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
            res = await _create_fup(eid, payload.message, payload.days_delay, payload.mode, payload.trigger_condition, user["user_id"])
            results.append(res)
        except Exception:
            continue
    return results

async def _create_fup(eid, message, days, mode, condition, user_id, custom_scheduled_at=None):
    em = await db.tracked_emails.find_one({"id": eid, "user_id": user_id}, {"_id": 0})
    if not em:
        raise HTTPException(404, "Tracked email not found")
    
    fid = uuid.uuid4().hex
    if custom_scheduled_at:
        scheduled = custom_scheduled_at
    else:
        sent_at = datetime.fromisoformat(em["sent_at"]) if isinstance(em["sent_at"], str) else em["sent_at"]
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        scheduled = sent_at + timedelta(days=days)

    doc = {
        "id": fid,
        "user_id": user_id,
        "tracked_email_id": eid,
        "recipient": em["recipient"],
        "subject": em["subject"],
        "message": message,
        "days_delay": days,
        "scheduled_at": scheduled.isoformat(),
        "mode": mode,
        "trigger_condition": condition,
        "sent": False,
        "sent_at": None,
    }
    await db.follow_ups.insert_one(doc)
    doc.pop("_id", None)
    return doc

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

@api_router.put("/automation-rules/{rid}")
async def update_rule(rid: str, payload: AutomationRuleCreate, user: dict = Depends(get_current_user)):
    res = await db.automation_rules.update_one(
        {"id": rid, "user_id": user["user_id"]},
        {"$set": {
            "name": payload.name,
            "stages": [s.model_dump() for s in payload.stages],
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}

@api_router.delete("/automation-rules/{rid}")
async def delete_rule(rid: str, user: dict = Depends(get_current_user)):
    await db.automation_rules.delete_one({"id": rid, "user_id": user["user_id"]})
    return {"ok": True}

@api_router.get("/follow-ups")
async def list_follow_ups(user: dict = Depends(get_current_user)):
    """List all follow-ups with their parent email's current status."""
    rows = await db.follow_ups.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("scheduled_at", 1).to_list(500)
    
    # Enrich with email status
    results = []
    for f in rows:
        em = await db.tracked_emails.find_one({"id": f["tracked_email_id"]}, {"_id": 0})
        if em:
            f["email_opened"] = em.get("open_count", 0) > 0
            f["email_replied"] = em.get("replied", False)
        results.append(f)
        
    return results

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
    return {"ok": True}

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

async def automation_worker():
    """Background task that sends due 'auto' follow-ups via Gmail API."""
    while True:
        try:
            # 1. Fetch due follow-ups that are in 'auto' mode and not yet sent
            now_iso = datetime.now(timezone.utc).isoformat()
            dues = await db.follow_ups.find({
                "sent": False,
                "mode": "auto",
                "scheduled_at": {"$lte": now_iso}
            }).to_list(50)
            
            for f in dues:
                # 2. Check conditions (if_not_opened, etc.)
                em = await db.tracked_emails.find_one({"id": f["tracked_email_id"]})
                if not em: continue
                
                # 2. PROACTIVE REPLY CHECK
                # Before sending ANY follow-up, we check Gmail one last time 
                # to see if the user replied but the extension hasn't seen it yet.
                is_replied = em.get("replied", False)
                if not is_replied and user.get("access_token") and em.get("gmail_thread_id"):
                    async with httpx.AsyncClient() as client:
                        thread_url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{em['gmail_thread_id']}"
                        r = await client.get(thread_url, headers={"Authorization": f"Bearer {user['access_token']}"})
                        if r.status_code == 200:
                            msgs = r.json().get("messages", [])
                            my_email = user["email"].lower()
                            for m in msgs:
                                hds = m.get("payload", {}).get("headers", [])
                                frm = next((h["value"].lower() for h in hds if h["name"].lower() == "from"), "")
                                if frm and my_email not in frm:
                                    # FOUND A REPLY!
                                    await db.tracked_emails.update_one({"id": em["id"]}, {"$set": {"replied": True}})
                                    await db.follow_ups.delete_many({"tracked_email_id": em["id"], "sent": False})
                                    is_replied = True
                                    logging.info(f"Proactive detection: Lead {em['recipient']} replied to {em['id']}. Automation stopped.")
                                    break

                cond = f.get("trigger_condition", "always")
                is_opened = em.get("open_count", 0) > 0
                
                should_send = False
                if cond == "always": 
                    should_send = True
                elif cond == "if_not_opened": 
                    should_send = not is_opened
                elif cond == "if_not_replied": 
                    should_send = not is_replied
                elif cond == "if_opened_no_reply":
                    should_send = is_opened and not is_replied
                
                if is_replied: should_send = False
                
                if should_send:
                    user = await db.users.find_one({"user_id": f["user_id"]})
                    if user and user.get("access_token"):
                        # 3. Inject tracking pixel
                        # Use the original TID for tracking
                        # We need a base URL for the pixel. 
                        # In production this should be a real domain.
                        # Find original thread and message ID for perfect threading
                        thread_id, parent_msg_id = await find_thread_info(user["access_token"], em["recipient"], em["subject"])
                        
                        # Use follow-up ID for pixel tracking
                        backend_url = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
                        pixel_url = f"{backend_url}/api/track/pixel/{f['id']}.png"
                        pixel_html = f'<img src="{pixel_url}" width="1" height="1" style="display:none;" />'
                        full_body = f"{f['message']}<br/><br/>{pixel_html}"
                        
                        success = await send_gmail_message(
                            user["access_token"], 
                            f["recipient"], 
                            f["subject"], 
                            full_body,
                            thread_id=thread_id,
                            parent_msg_id=parent_msg_id
                        )
                        if success:
                            # 4. Mark as sent
                            await db.follow_ups.update_one(
                                {"id": f["id"]},
                                {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()}}
                            )
                            await db.tracked_emails.update_one(
                                {"id": em["id"]},
                                {"$inc": {"follow_up_count": 1}}
                            )
                            logging.info(f"Auto follow-up sent to {f['recipient']} for {em['id']}")
        except Exception as e:
            logging.error(f"Automation worker error: {e}")
            
        await asyncio.sleep(60) # Run every minute

async def check_all_replies():
    """Background task to scan ALL pending emails for replies."""
    while True:
        try:
            # Find emails that haven't been replied to yet
            pending = await db.tracked_emails.find({"replied": {"$ne": True}}).to_list(1000)
            
            for em in pending:
                user = await db.users.find_one({"user_id": em["user_id"]})
                if not user or not user.get("access_token"):
                    continue
                
                tid = em.get("gmail_thread_id")
                
                # 1. DISCOVERY: If we don't have a thread ID, try to find it
                if not tid:
                    tid, _ = await find_thread_info(user["access_token"], em["recipient"], em["subject"])
                    if tid:
                        await db.tracked_emails.update_one({"id": em["id"]}, {"$set": {"gmail_thread_id": tid}})
                        logging.info(f"Auto-Discovery: Linked thread {tid} for email {em['id']}")

                # 2. SCAN: If we have a thread ID, check for replies
                if tid:
                    async with httpx.AsyncClient() as client:
                        thread_url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{tid}"
                        r = await client.get(thread_url, headers={"Authorization": f"Bearer {user['access_token']}"})
                        if r.status_code == 200:
                            msgs = r.json().get("messages", [])
                            my_email = user["email"].lower()
                            found_reply = False
                            for m in msgs:
                                hds = m.get("payload", {}).get("headers", [])
                                frm = next((h["value"].lower() for h in hds if h["name"].lower() == "from"), "")
                                if frm and my_email not in frm:
                                    found_reply = True
                                    break
                            
                            if found_reply:
                                await db.tracked_emails.update_one({"id": em["id"]}, {"$set": {"replied": True}})
                                await db.follow_ups.delete_many({"tracked_email_id": em["id"], "sent": False})
                                logging.info(f"Background Alert: Lead {em['recipient']} reply detected! Promoted to Active.")
                                
                                push_event(user["user_id"], {
                                    "type": "reply",
                                    "tracked_id": em["id"],
                                    "recipient": em["recipient"],
                                    "subject": em["subject"],
                                    "ts": datetime.now(timezone.utc).isoformat()
                                })
            
            # Run frequently (every 60s) for responsive updates
            await asyncio.sleep(60) 
        except Exception as e:
            logging.error(f"Reply checker error: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(automation_worker())
    asyncio.create_task(check_all_replies())

# ---------- SSE notifications ----------
@api_router.get("/events/stream")
async def events_stream(request: Request, token: Optional[str] = None, key: Optional[str] = None):
    # Allow token via query for EventSource
    user = None
    if token:
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    elif key:
        user = await db.users.find_one({"ext_api_key": key}, {"_id": 0})
        
    if not user:
        try:
            user = await get_current_user(request)
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

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[o.strip().strip('"').strip("'") for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()],
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "Content-Type", "X-Ext-Key"],
)

app.include_router(api_router)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

# Force uvicorn reload to pick up .env changes
