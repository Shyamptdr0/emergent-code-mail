import os
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def migrate_rules():
    client = AsyncIOMotorClient("mongodb+srv://shyam8patidar_db_user:ZKhd4aH0sdwoukkb@cluster0.8flb9cw.mongodb.net/?appName=Cluster0")
    db = client["test_database"]
    
    # Update all stages in all rules where time is "09:00" to be empty ""
    rules = await db.automation_rules.find().to_list(100)
    for rule in rules:
        modified = False
        for stage in rule.get("stages", []):
            if stage.get("time") == "09:00":
                stage["time"] = ""
                modified = True
        
        if modified:
            await db.automation_rules.update_one({"_id": rule["_id"]}, {"$set": {"stages": rule["stages"]}})
            print(f"Migrated rule: {rule.get('name')}")

if __name__ == "__main__":
    asyncio.run(migrate_rules())
