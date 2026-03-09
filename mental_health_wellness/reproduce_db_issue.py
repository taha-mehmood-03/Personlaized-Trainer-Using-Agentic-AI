
import asyncio
import sys
import os
from datetime import datetime

import sys
import os
from datetime import datetime

# Add the package directory to path to allow direct submodule imports
sys.path.append(os.path.join(os.getcwd(), "src", "mental_health_wellness"))

from dotenv import load_dotenv
load_dotenv()

# Import directly from db module, bypassing top-level package init
from db.client import get_prisma_client, ensure_user_exists, create_new_session

async def main():
    print("Starting reproduction script...")
    
    try:
        prisma = await get_prisma_client()
        print("Connected to Prisma")
        
        # 1. Ensure User Exists
        user_id = "test_user_repro"
        print(f"Ensuring user {user_id} exists...")
        user = await ensure_user_exists(user_id, "test_repro@example.com", "Test Repro User")
        print(f"User: {user}")
        
        # 2. Create Session
        print("Creating new session...")
        session = await create_new_session(user_id, "Test Repro Session")
        session_id = session["id"]
        print(f"Session created: {session_id}")
        
        # 3. Create Message directly (mimicking save_session logic)
        print("Creating message...")
        msg_content = "Hello from reproduction script"
        message = await prisma.message.create(
            data={
                "sessionId": session_id,
                "role": "USER",
                "content": msg_content,
                "emotion": "NEUTRAL"
            }
        )
        print(f"Message created: {message.id}")
        
        # 4. Retrieve Message (mimicking intake logic)
        print("Retrieving messages for session...")
        messages = await prisma.message.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"}
        )
        print(f"Found {len(messages)} messages.")
        for m in messages:
            print(f" - [{m.role}] {m.content}")
            
        if len(messages) == 1 and messages[0].content == msg_content:
            print("SUCCESS: Data saved and retrieved correctly.")
        else:
            print("FAILURE: Data not retrieved correctly.")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        from mental_health_wellness.db.client import close_prisma_client
        await close_prisma_client()

if __name__ == "__main__":
    asyncio.run(main())
