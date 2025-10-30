import asyncio, os, uuid, sys
sys.path.append("src")
from bus import subscribe_envelopes

async def handle(env: dict):
    print("Verified envelope:")
    print("  kind:", env["kind"])
    print("  lamport:", env["lamport"])
    print("  payload:", env["payload"])

async def main():
    thread_id = os.getenv("THREAD_ID", "demo-thread")
    subject = f"thread.{thread_id}.planner"
    print("Listening for ENVELOPES on", subject)
    await subscribe_envelopes(thread_id, subject, handle)

if __name__ == "__main__":
    asyncio.run(main())
