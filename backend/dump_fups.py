import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

async def run():
    emails = await db.tracked_emails.find().to_list(100)
    for em in emails:
        tid = em["id"]
        print(f"\nEmail: {em.get('subject', 'No Subject')} (replied={em.get('replied')}, open_count={em.get('open_count')})")
        fups = await db.follow_ups.find({"tracked_email_id": tid}).sort("scheduled_at", 1).to_list(100)
        for f in fups:
            print(f"  FUP: {f['subject']} - Sent: {f['sent']} - Cond: {f['trigger_condition']}")

if __name__ == "__main__":
    asyncio.run(run())
