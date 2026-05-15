import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    rules = await db.automation_rules.find().to_list(10)
    print(f"{'Rule Name':<20} | {'Stages'}")
    print("-" * 60)
    for r in rules:
        stages = r.get('stages', [])
        print(f"{r['name']:<20} | {len(stages)} stages")
        for s in stages:
            print(f"  - {s.get('trigger')} | {s.get('delay_value') or s.get('days')} {s.get('delay_unit', 'days')} | {s.get('time')}")

if __name__ == "__main__":
    asyncio.run(check())
