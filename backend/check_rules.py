import os
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import json

async def check_rules():
    client = AsyncIOMotorClient("mongodb+srv://shyam8patidar_db_user:ZKhd4aH0sdwoukkb@cluster0.8flb9cw.mongodb.net/?appName=Cluster0")
    db = client["test_database"]
    rules = await db.automation_rules.find().to_list(100)
    for r in rules:
        r["_id"] = str(r["_id"])
        print(json.dumps(r, indent=2))

if __name__ == "__main__":
    asyncio.run(check_rules())
