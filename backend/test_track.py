import asyncio
import httpx

async def f():
    async with httpx.AsyncClient() as client:
        # We need a valid ext key, let's look up one
        from motor.motor_asyncio import AsyncIOMotorClient
        import os
        from dotenv import load_dotenv
        load_dotenv()
        mongo_url = os.environ['MONGO_URL']
        db = AsyncIOMotorClient(mongo_url)[os.environ['DB_NAME']]
        user = await db.users.find_one({})
        ext_key = user['ext_api_key']
        
        r = await client.post('http://127.0.0.1:8001/api/track/create', json={'recipient': 'test@test.com', 'subject': 'Test', 'message_preview': 'Test'}, headers={'X-Ext-Key': ext_key})
        print("CREATE", r.status_code, r.text)
        
        if r.status_code == 200:
            tid = r.json()['id']
            r2 = await client.post(f'http://127.0.0.1:8001/api/track/update/{tid}', json={'recipient': 'test@test.com', 'subject': 'Test', 'message_preview': 'Test'}, headers={'X-Ext-Key': ext_key})
            print("UPDATE", r2.status_code, r2.text)

if __name__ == "__main__":
    asyncio.run(f())
