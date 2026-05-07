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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

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

class FollowUpCreate(BaseModel):
    tracked_email_id: str
    message: str
    days_delay: int = 3
    mode: str = "manual"  # 'manual' or 'auto'

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

async def get_user_by_ext_key(x_ext_key: Optional[str] = Header(None)) -> dict:
    if not x_ext_key:
        raise HTTPException(status_code=401, detail="Missing extension key")
    user = await db.users.find_one({"ext_api_key": x_ext_key}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid extension key")
    return user

# ---------- Auth endpoints ----------
class SessionExchange(BaseModel):
    session_id: str

@api_router.post("/auth/session")
async def auth_session(payload: SessionExchange, response: Response):
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = r.json()
    email = data["email"]
    name = data.get("name", email)
    picture = data.get("picture")
    session_token = data["session_token"]

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        ext_api_key = existing.get("ext_api_key") or secrets.token_urlsafe(24)
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "ext_api_key": ext_api_key}},
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
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

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
        "sender_ip": sender_ip,
        "open_count": 0,
        "scan_count": 0,
        "last_opened_at": None,
        "opens": [],
        "scans": [],
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
    if updates:
        await db.tracked_emails.update_one(
            {"id": tid, "user_id": user["user_id"]},
            {"$set": updates},
        )
    return {"ok": True}

class HeartbeatViewing(BaseModel):
    tracked_ids: List[str]

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
    1) Sets self_viewing_until = now + 90s (forward filter)
    2) Retroactively reclassifies opens from the last 60s as scans (covers race
       condition where Gmail loaded pixel before extension could ping)."""
    now = datetime.now(timezone.utc)
    until = (now + timedelta(seconds=90)).isoformat()
    cutoff = (now - timedelta(seconds=60)).isoformat()

    em = await db.tracked_emails.find_one(
        {"id": tid, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not em:
        return {"ok": False, "error": "not_found"}

    opens = em.get("opens", [])
    scans = em.get("scans", [])
    keep_opens = []
    moved = 0
    for o in opens:
        if o.get("ts", "") >= cutoff:
            scans.append({**o, "self_view_retro": True})
            moved += 1
        else:
            keep_opens.append(o)

    last_opened = keep_opens[-1]["ts"] if keep_opens else None
    await db.tracked_emails.update_one(
        {"id": tid, "user_id": user["user_id"]},
        {"$set": {
            "self_viewing_until": until,
            "opens": keep_opens,
            "open_count": len(keep_opens),
            "last_opened_at": last_opened,
            "scans": scans,
            "scan_count": len(scans),
        }},
    )
    return {"ok": True, "self_viewing_until": until, "moved_to_scans": moved}

@api_router.get("/track/pixel/{tid}.png")
async def track_pixel(tid: str, request: Request):
    em = await db.tracked_emails.find_one({"id": tid}, {"_id": 0})
    if em:
        ua = request.headers.get("user-agent", "")
        ip = get_client_ip(request)
        ts = datetime.now(timezone.utc).isoformat()

        sent_at_raw = em.get("sent_at")
        sent_at = datetime.fromisoformat(sent_at_raw) if isinstance(sent_at_raw, str) else sent_at_raw
        if sent_at and sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        seconds_since_send = (datetime.now(timezone.utc) - sent_at).total_seconds() if sent_at else 9999

        # Check self-viewing window — sender is currently looking at this email in Gmail
        self_viewing_raw = em.get("self_viewing_until")
        self_viewing_until = None
        if self_viewing_raw:
            self_viewing_until = datetime.fromisoformat(self_viewing_raw) if isinstance(self_viewing_raw, str) else self_viewing_raw
            if self_viewing_until and self_viewing_until.tzinfo is None:
                self_viewing_until = self_viewing_until.replace(tzinfo=timezone.utc)
        is_self_viewing = bool(self_viewing_until and self_viewing_until > datetime.now(timezone.utc))

        # IP + UA based classification:
        sender_ip = em.get("sender_ip", "")
        scanner_ip_prefixes = ("66.249.", "64.233.", "209.85.", "72.14.", "216.58.", "172.217.")
        is_google_scanner_ip = ip.startswith(scanner_ip_prefixes) if ip else False
        is_image_proxy = ("GoogleImageProxy" in ua) or ("ggpht.com" in ua)

        is_scan = (
            seconds_since_send < 2                      # 2s grace covers immediate Gmail scan
            or is_self_viewing                          # explicit thread-view ping from extension
            # or (sender_ip and ip and sender_ip == ip) # Disabled so user can test between accounts on same device
            or (is_google_scanner_ip and not is_image_proxy)
            or "Google-Read-Aloud" in ua
            or "GoogleSafetyCenter" in ua
            or "Slackbot-LinkExpanding" in ua
            or "bingbot" in ua.lower()
            or "facebookexternalhit" in ua.lower()
        )

        print(f"[DEBUG] tid={tid} ip={ip} is_scan={is_scan} ua={ua[:50]} proxy={is_image_proxy}")

        if is_scan:
            await db.tracked_emails.update_one(
                {"id": tid},
                {
                    "$inc": {"scan_count": 1},
                    "$push": {"scans": {"ts": ts, "ua": ua, "ip": ip, "seconds_since_send": seconds_since_send}},
                },
            )
        else:
            await db.tracked_emails.update_one(
                {"id": tid},
                {
                    "$inc": {"open_count": 1},
                    "$set": {"last_opened_at": ts},
                    "$push": {"opens": {"ts": ts, "ua": ua, "ip": ip}},
                },
            )
            push_event(em["user_id"], {
                "type": "open",
                "tracked_id": tid,
                "recipient": em["recipient"],
                "subject": em["subject"],
                "ts": ts,
            })

    headers = {
        "Content-Type": "image/png",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return FastResponse(content=PIXEL_PNG, media_type="image/png", headers=headers)

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
    em = await db.tracked_emails.find_one(
        {"id": payload.tracked_email_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not em:
        raise HTTPException(404, "Tracked email not found")
    fid = uuid.uuid4().hex
    sent_at = datetime.fromisoformat(em["sent_at"]) if isinstance(em["sent_at"], str) else em["sent_at"]
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    scheduled = sent_at + timedelta(days=payload.days_delay)
    doc = {
        "id": fid,
        "user_id": user["user_id"],
        "tracked_email_id": payload.tracked_email_id,
        "recipient": em["recipient"],
        "subject": em["subject"],
        "message": payload.message,
        "days_delay": payload.days_delay,
        "scheduled_at": scheduled.isoformat(),
        "mode": payload.mode,
        "sent": False,
        "sent_at": None,
    }
    await db.follow_ups.insert_one(doc)
    doc.pop("_id", None)
    return {k: v for k, v in doc.items()}

@api_router.get("/follow-ups")
async def list_follow_ups(user: dict = Depends(get_current_user)):
    rows = await db.follow_ups.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("scheduled_at", 1).to_list(500)
    return rows

@api_router.get("/follow-ups/due")
async def due_follow_ups(user: dict = Depends(get_user_by_ext_key)):
    """Extension polls for due follow-ups whose tracked email has NOT been replied/opened-replied."""
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = await db.follow_ups.find({
        "user_id": user["user_id"],
        "sent": False,
        "scheduled_at": {"$lte": now_iso},
    }, {"_id": 0}).to_list(50)
    return rows

@api_router.post("/follow-ups/{fid}/mark-sent")
async def mark_sent(fid: str, user: dict = Depends(get_current_user)):
    res = await db.follow_ups.update_one(
        {"id": fid, "user_id": user["user_id"]},
        {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}

@api_router.post("/follow-ups/{fid}/mark-sent-ext")
async def mark_sent_ext(fid: str, user: dict = Depends(get_user_by_ext_key)):
    await db.follow_ups.update_one(
        {"id": fid, "user_id": user["user_id"]},
        {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}

@api_router.delete("/follow-ups/{fid}")
async def delete_follow_up(fid: str, user: dict = Depends(get_current_user)):
    await db.follow_ups.delete_one({"id": fid, "user_id": user["user_id"]})
    return {"ok": True}

# ---------- SSE notifications ----------
@api_router.get("/events/stream")
async def events_stream(request: Request, token: Optional[str] = None):
    # Allow token via query for EventSource (cannot send headers/cookies cross-site reliably)
    user = None
    if token:
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
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
                    msg = await asyncio.wait_for(queue.get(), timeout=20)
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
        "X-Accel-Buffering": "no",
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
