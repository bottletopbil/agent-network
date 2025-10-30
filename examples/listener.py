import asyncio, os, uuid
import sys
sys.path.append("src")
from bus import subscribe

async def handle(msg: dict):
    print("Got:", msg)

async def main():
    thread_id = os.getenv("THREAD_ID", "demo-thread")  # match publisher env to see same thread
    subject = f"thread.{thread_id}.planner"
    print("Listening on", subject)
    await subscribe(thread_id, subject, handle)

if __name__ == "__main__":
    asyncio.run(main())
