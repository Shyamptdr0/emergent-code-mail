import os
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from datetime import datetime, timedelta, timezone

def get_next_business_time(dt, days_offset, target_hour=None):
    target = dt + timedelta(days=days_offset)
    if target.weekday() >= 5:
        days_to_monday = (7 - target.weekday()) % 7
        target = target + timedelta(days=days_to_monday)
        target = target.replace(hour=10, minute=0, second=0, microsecond=0)
    elif target_hour is not None:
        target = target.replace(hour=target_hour)
    return target

async def fix_fups():
    client = AsyncIOMotorClient("mongodb+srv://shyam8patidar_db_user:ZKhd4aH0sdwoukkb@cluster0.8flb9cw.mongodb.net/?appName=Cluster0")
    db = client["test_database"]
    
    fups = await db.follow_ups.find({"sent": False}).to_list(100)
    for f in fups:
        em = await db.tracked_emails.find_one({"id": f["tracked_email_id"]})
        if not em: continue
        
        sent_at = datetime.fromisoformat(em["sent_at"])
        if sent_at.tzinfo is None: sent_at = sent_at.replace(tzinfo=timezone.utc)
        
        # If the follow-up 'time' is "09:00" or empty, we use the original time
        time_val = f.get("time")
        if time_val == "09:00": time_val = "" # Migration
        
        hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else None
        new_sched = get_next_business_time(sent_at, f["days_delay"], target_hour=hour)
        
        if f["scheduled_at"] != new_sched.isoformat():
            await db.follow_ups.update_one({"_id": f["_id"]}, {"$set": {"scheduled_at": new_sched.isoformat(), "time": time_val}})
            print(f"Rescheduled FUP {f['id']} from {f['scheduled_at']} to {new_sched.isoformat()}")

if __name__ == "__main__":
    asyncio.run(fix_fups())
