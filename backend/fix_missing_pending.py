import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import uuid
from datetime import datetime, timezone, timedelta

load_dotenv()
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

def get_next_business_time(dt: datetime, days_offset: int, target_hour=None):
    target = dt + timedelta(days=days_offset)
    if target.weekday() >= 5: # Sat or Sun
        days_to_monday = (7 - target.weekday()) % 7
        target = target + timedelta(days=days_to_monday)
        
    if target_hour is not None:
        target = target.replace(hour=target_hour)
    return target

async def run():
    print("Finding missing follow-ups...")
    emails = await db.tracked_emails.find({"replied": {"$ne": True}}).to_list(1000)
    
    for em in emails:
        tid = em["id"]
        user_id = em["user_id"]
        
        sent_count = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": True})
        pending_count = await db.follow_ups.count_documents({"tracked_email_id": tid, "sent": False})
        
        if pending_count > 0:
            continue
            
        rules = await db.automation_rules.find({"user_id": user_id}).sort([("updated_at", -1), ("created_at", -1)]).to_list(1)
        all_stages = rules[0].get("stages", []) if rules else []
        
        if not all_stages: continue
        
        if sent_count < len(all_stages):
            next_stage = all_stages[sent_count]
            trigger = next_stage.get("trigger", "no_reply")
            if trigger == "no_open": cond = "if_no_open"
            elif trigger == "opened_no_reply": cond = "if_opened_no_reply"
            else: cond = f"if_{trigger}"
            
            now_dt = datetime.now(timezone.utc)
            delay = next_stage.get("days", 1)
            time_val = next_stage.get("time")
            hour = int(time_val.split(":")[0]) if time_val and ":" in time_val else now_dt.hour
            
            new_sched = get_next_business_time(now_dt, delay, target_hour=hour)
            
            fid = uuid.uuid4().hex
            doc = {
                "id": fid,
                "user_id": user_id,
                "tracked_email_id": tid,
                "recipient": em["recipient"],
                "subject": em.get("subject", ""),
                "message": next_stage["message"],
                "days_delay": delay,
                "scheduled_at": new_sched.isoformat(),
                "mode": "auto",
                "trigger_condition": cond,
                "time": time_val,
                "sent": False,
                "sent_at": None,
            }
            await db.follow_ups.insert_one(doc)
            print(f"Fixed missing sequence: Added stage {sent_count+1} as pending for {tid}")

if __name__ == "__main__":
    asyncio.run(run())
