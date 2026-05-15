import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def check():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    fups = await db.follow_ups.find({"sent": False}).to_list(20)
    print(f"{'ID':<32} | {'Scheduled At':<25} | {'Condition':<20} | {'Weekday'}")
    print("-" * 90)
    for f in fups:
        dt = datetime.fromisoformat(f['scheduled_at'])
        print(f"{f['id']:<32} | {f['scheduled_at']:<25} | {f.get('trigger_condition'):<20} | {dt.strftime('%A')}")

if __name__ == "__main__":
    asyncio.run(check())
