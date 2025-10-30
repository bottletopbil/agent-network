import asyncio, os, uuid
import sys
sys.path.append("src")
from bus import publish

async def main():
    thread_id = os.getenv("THREAD_ID", str(uuid.uuid4()))
    subject = f"thread.{thread_id}.planner"
    message = {"hello": "world", "n": 1}
    await publish(thread_id, subject, message)
    print("Published:", subject, message)

if __name__ == "__main__":
    asyncio.run(main())
