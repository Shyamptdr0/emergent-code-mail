import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def check():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    # Get recent emails
    emails = await db.tracked_emails.find().sort("created_at", -1).to_list(10)
    print(f"{'Email ID':<32} | {'Recipient':<20} | {'Open Count':<5} | {'FUPs'}")
    print("-" * 80)
    for e in emails:
        fups = await db.follow_ups.find({"tracked_email_id": e["id"]}).to_list(20)
        fup_info = ", ".join([f"{f.get('trigger_condition')}({f.get('sent')})" for f in fups])
        print(f"{e['id']:<32} | {e['recipient']:<20} | {e.get('open_count', 0):<10} | {fup_info}")

if __name__ == "__main__":
    asyncio.run(check())
