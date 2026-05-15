import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    uid = "user_8fcdd538b409"
    rules = await db.automation_rules.find({"user_id": uid}).to_list(100)
    for r in rules:
        print(f"Rule: {r['name']}")
        for s in r.get('stages', []):
            print(f"  Stage: {s}")

if __name__ == "__main__":
    asyncio.run(check())
