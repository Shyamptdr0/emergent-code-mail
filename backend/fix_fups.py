import os
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pathlib import Path

# Load env from parent dir
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

def get_next_business_time(dt, offset, unit="days", target_hour=None):
    if unit == "hours":
        target = dt + timedelta(hours=offset)
    else:
        target = dt + timedelta(days=offset)
        
    if target.weekday() >= 5: # Saturday or Sunday
        days_to_monday = (7 - target.weekday()) % 7
        target = target + timedelta(days=days_to_monday)
        
    if target_hour is not None and unit == "days":
        target = target.replace(hour=target_hour)
    return target

async def fix_fups():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print(f"Connected to {db_name}. Scanning for pending follow-ups...")
    
    # Find all follow-ups that are not sent and not completed
    fups = await db.follow_ups.find({"sent": False, "completed": False}).to_list(500)
    count = 0
    
    for f in fups:
        em = await db.tracked_emails.find_one({"id": f["tracked_email_id"]})
        if not em: continue
        
        # Use sent_at of the parent email as the base for the first follow-up
        # Or use now() if it's a cascading one? 
        # Actually, the logic in the server uses sent_at for upfront ones and now() for cascading ones.
        # To be safe, we check if the current scheduled_at is on a weekend.
        
        curr_sched = datetime.fromisoformat(f["scheduled_at"])
        if curr_sched.tzinfo is None: curr_sched = curr_sched.replace(tzinfo=timezone.utc)
        
        if curr_sched.weekday() >= 5:
            # It's on a weekend! Shift it to Monday.
            days_to_monday = (7 - curr_sched.weekday()) % 7
            new_sched = curr_sched + timedelta(days=days_to_monday)
            
            await db.follow_ups.update_one(
                {"_id": f["_id"]}, 
                {"$set": {"scheduled_at": new_sched.isoformat()}}
            )
            print(f"FIXED: FUP {f['id']} (Subject: {f.get('subject')}) shifted from {f['scheduled_at']} to {new_sched.isoformat()}")
            count += 1
            
    print(f"Finished. Total follow-ups fixed: {count}")

if __name__ == "__main__":
    asyncio.run(fix_fups())
