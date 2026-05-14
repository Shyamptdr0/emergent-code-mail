import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

async def run():
    rules = await db.automation_rules.find().to_list(100)
    for r in rules:
        print(f"Rule: {r['name']} - Stages: {len(r.get('stages', []))}")
        for s in r.get('stages', []):
            print(f"  Stage: {s}")

if __name__ == "__main__":
    asyncio.run(run())
