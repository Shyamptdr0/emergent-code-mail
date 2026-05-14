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
    
    users = await db.users.find({}, {"user_id": 1}).to_list(100)
    for u in users:
        user_id = u["user_id"]
        
        # 1. Fetch ALL existing rules to find custom messages
        old_rules = await db.automation_rules.find({"user_id": user_id}).to_list(10)
        
        no_open_messages = []
        open_reply_messages = []
        
        for rule in old_rules:
            for stage in rule.get("stages", []):
                msg = stage.get("message", "")
                if not msg: continue
                
                trigger = stage.get("trigger", "")
                if trigger == "no_open":
                    if msg not in no_open_messages: no_open_messages.append(msg)
                elif trigger == "opened_no_reply":
                    if msg not in open_reply_messages: open_reply_messages.append(msg)
        
        # Fallbacks if no messages found
        if not no_open_messages: no_open_messages = ["Hi, just checking if you saw my previous email?"]
        if not open_reply_messages: open_reply_messages = ["I see you opened my email, just following up!"]
        
        # 2. Build the 1-3-5 sequence using these messages
        # Use first no_open message for all 3 stages as requested
        no_msg = no_open_messages[0]
        
        # Use up to 3 different open_no_reply messages if available
        o_msg1 = open_reply_messages[0]
        o_msg2 = open_reply_messages[1] if len(open_reply_messages) > 1 else o_msg1
        o_msg3 = open_reply_messages[2] if len(open_reply_messages) > 2 else (open_reply_messages[1] if len(open_reply_messages) > 1 else o_msg1)
        
        no_open_stages = [
            {"trigger": "no_open", "days": 1, "time": "", "message": no_msg},
            {"trigger": "no_open", "days": 3, "time": "", "message": no_msg},
            {"trigger": "no_open", "days": 5, "time": "", "message": no_msg},
        ]
        
        opened_no_reply_stages = [
            {"trigger": "opened_no_reply", "days": 1, "time": "", "message": o_msg1},
            {"trigger": "opened_no_reply", "days": 3, "time": "", "message": o_msg2},
            {"trigger": "opened_no_reply", "days": 5, "time": "", "message": o_msg3}
        ]
        
        # 3. Wipe and replace with two separate rules
        await db.automation_rules.delete_many({"user_id": user_id})
        
        import uuid
        from datetime import datetime, timezone
        
        await db.automation_rules.insert_one({
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "name": "Sequence: Not Open",
            "stages": no_open_stages,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        await db.automation_rules.insert_one({
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "name": "Sequence: Open but No Reply",
            "stages": opened_no_reply_stages,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        print(f"Updated rules with split sequences for user {user_id}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(update_rules())
