import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    eid = "3cec0149e78d4bbeb6360311bc3130e1"
    email = await db.tracked_emails.find_one({"id": eid})
    if not email:
        print("Email not found")
        return
        
    print(f"Email: {email['subject']} | Recipient: {email['recipient']} | User ID: {email['user_id']}")
    
    fups = await db.follow_ups.find({"tracked_email_id": eid}).to_list(100)
    print(f"Follow-ups found: {len(fups)}")
    for f in fups:
        print(f"  - ID: {f['id']} | Cond: {f['trigger_condition']} | Sent: {f['sent']} | Sched: {f['scheduled_at']}")
        
    rules = await db.automation_rules.find({"user_id": email['user_id']}).to_list(100)
    print(f"Rules for this user: {len(rules)}")
    for r in rules:
        print(f"  - Rule: {r['name']} | Stages: {len(r.get('stages', []))}")

if __name__ == "__main__":
    asyncio.run(check())
