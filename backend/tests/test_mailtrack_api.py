"""MailTrack backend API regression tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://track-open-1.preview.emergentagent.com').rstrip('/')

SESSION_TOKEN = "test_session_1777984514110"
EXT_KEY = "test_ext_key_1777984514110"
USER_ID = "test-user-1777984514110"
TRACKED_ID = "trk_1777984514142"


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {SESSION_TOKEN}"}


@pytest.fixture
def ext_headers():
    return {"X-Ext-Key": EXT_KEY}


# Auth basics
class TestAuth:
    def test_me_unauth_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_me_with_bearer(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user_id"] == USER_ID
        assert d["ext_api_key"] == EXT_KEY
        assert "_id" not in d

    def test_rotate_ext_key(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/auth/rotate-ext-key", headers=auth_headers)
        assert r.status_code == 200
        new_key = r.json()["ext_api_key"]
        assert new_key and new_key != EXT_KEY
        # restore
        import pymongo
        pymongo.MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))['test_database'].users.update_one(
            {"user_id": USER_ID}, {"$set": {"ext_api_key": EXT_KEY}}
        )


# Tracking pixel + create
class TestTracking:
    def test_track_create_requires_ext_key(self):
        r = requests.post(f"{BASE_URL}/api/track/create", json={"recipient": "x@y.com", "subject": "S"})
        assert r.status_code == 401

    def test_track_create_with_ext_key(self, ext_headers):
        r = requests.post(f"{BASE_URL}/api/track/create", headers=ext_headers,
                          json={"recipient": "TEST_x@y.com", "subject": "TEST_Subject", "message_preview": "p"})
        assert r.status_code == 200
        d = r.json()
        assert "id" in d and "pixel_url" in d
        assert d["pixel_url"].endswith(f"/api/track/pixel/{d['id']}.png")

    def test_pixel_returns_png_and_increments(self, auth_headers):
        # Get current count
        r0 = requests.get(f"{BASE_URL}/api/emails/{TRACKED_ID}", headers=auth_headers)
        assert r0.status_code == 200
        before = r0.json()["open_count"]
        # Hit pixel
        r = requests.get(f"{BASE_URL}/api/track/pixel/{TRACKED_ID}.png")
        assert r.status_code == 200
        assert r.headers.get("content-type") == "image/png"
        assert len(r.content) > 0 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
        # Verify increment
        r2 = requests.get(f"{BASE_URL}/api/emails/{TRACKED_ID}", headers=auth_headers)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["open_count"] == before + 1
        assert d2["last_opened_at"] is not None
        assert "_id" not in d2


# Email lists
class TestEmails:
    def test_list_emails_auth(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/emails", headers=auth_headers)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert any(e["id"] == TRACKED_ID for e in rows)
        for e in rows:
            assert "_id" not in e

    def test_list_emails_unauth(self):
        r = requests.get(f"{BASE_URL}/api/emails")
        assert r.status_code == 401

    def test_emails_by_ext(self, ext_headers):
        r = requests.get(f"{BASE_URL}/api/emails/by-ext", headers=ext_headers)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        for e in rows:
            assert "_id" not in e

    def test_emails_by_ext_unauth(self):
        r = requests.get(f"{BASE_URL}/api/emails/by-ext")
        assert r.status_code == 401


# Follow-ups
class TestFollowUps:
    def test_create_list_mark_delete(self, auth_headers, ext_headers):
        # Create
        r = requests.post(f"{BASE_URL}/api/follow-ups", headers=auth_headers,
                          json={"tracked_email_id": TRACKED_ID, "message": "TEST_followup",
                                "days_delay": 1, "mode": "manual"})
        assert r.status_code == 200, r.text
        d = r.json()
        fid = d["id"]
        assert d["scheduled_at"] is not None
        assert d["sent"] is False
        assert d["recipient"] == "rcv@example.com"

        # List
        r2 = requests.get(f"{BASE_URL}/api/follow-ups", headers=auth_headers)
        assert r2.status_code == 200
        assert any(f["id"] == fid for f in r2.json())

        # Due (sent_at was 5d ago + 1 day delay = 4d ago, should be due)
        r3 = requests.get(f"{BASE_URL}/api/follow-ups/due", headers=ext_headers)
        assert r3.status_code == 200
        assert any(f["id"] == fid for f in r3.json())

        # Mark sent
        r4 = requests.post(f"{BASE_URL}/api/follow-ups/{fid}/mark-sent", headers=auth_headers)
        assert r4.status_code == 200

        # Verify persisted
        r5 = requests.get(f"{BASE_URL}/api/follow-ups", headers=auth_headers)
        match = [f for f in r5.json() if f["id"] == fid][0]
        assert match["sent"] is True
        assert match["sent_at"] is not None

        # Delete
        r6 = requests.delete(f"{BASE_URL}/api/follow-ups/{fid}", headers=auth_headers)
        assert r6.status_code == 200
        r7 = requests.get(f"{BASE_URL}/api/follow-ups", headers=auth_headers)
        assert not any(f["id"] == fid for f in r7.json())

    def test_create_followup_invalid_tracked(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/follow-ups", headers=auth_headers,
                          json={"tracked_email_id": "nonexistent", "message": "x", "days_delay": 1})
        assert r.status_code == 404


class TestStats:
    def test_stats(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/stats", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ["total_sent", "total_opened", "open_rate", "follow_ups_pending"]:
            assert k in d
        assert d["total_sent"] >= 1
        assert d["total_opened"] >= 1
