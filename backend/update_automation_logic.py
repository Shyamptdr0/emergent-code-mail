import motor.motor_asyncio
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

async def update_rules():
    load_dotenv(Path(__file__).parent / '.env')
    mongo_url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Update 'Open but not reply' rule to 1-3-5 sequence for the current user
    # Since we don't have user_id easily, let's find ALL rules with this name
    cursor = db.automation_rules.find({"name": "Open but not reply"})
    async for rule in cursor:
        new_stages = [
            {"trigger": "opened_no_reply", "days": 1, "time": "", "message": "hello please reply on my mail"},
            {"trigger": "opened_no_reply", "days": 3, "time": "", "message": "Gentle reminder regarding my previous mail."},
            {"trigger": "opened_no_reply", "days": 5, "time": "", "message": "I haven't heard back from you, just following up one last time."}
        ]
        await db.automation_rules.update_one(
            {"_id": rule["_id"]},
            {"$set": {"stages": new_stages}}
        )
        print(f"Updated rule '{rule['name']}' (ID: {rule.get('id')}) to 1-3-5 sequence.")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(update_rules())
