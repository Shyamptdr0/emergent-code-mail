import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

async def run():
    # Find the most recent tracked email
    em = await db.tracked_emails.find().sort("sent_at", -1).to_list(1)
    if not em:
        print("No emails found")
        return
    
    tid = em[0]['id']
    print(f"Tracking ID: {tid}")
    print(f"Recipient: {em[0]['recipient']}")
    print(f"Sent at: {em[0]['sent_at']}")
    print(f"Open Count: {em[0]['open_count']}")
    print(f"Replied: {em[0]['replied']}")
    
    # Find follow-ups for this email
    fups = await db.follow_ups.find({"tracked_email_id": tid}).sort("scheduled_at", 1).to_list(100)
    print(f"Follow-ups found: {len(fups)}")
    for f in fups:
        print(f"  ID: {f['id']}, Trigger: {f['trigger_condition']}, Days: {f['days_delay']}, Scheduled: {f['scheduled_at']}, Sent: {f['sent']}")

if __name__ == "__main__":
    asyncio.run(run())
