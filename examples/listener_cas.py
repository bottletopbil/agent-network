import asyncio, os, uuid, sys
sys.path.append("src")
from bus import subscribe_envelopes
from cas import has_blob, get_json

async def handle(env: dict):
    p = env["payload"]
    h = p.get("artifact_hash")
    print("Envelope OK:")
    print("  kind:", env["kind"])
    print("  lamport:", env["lamport"])
    print("  artifact_hash:", h)

    if h and has_blob(h):
        obj = get_json(h)
        print("  fetched artifact:", obj)
    else:
        print("  artifact missing from CAS")

async def main():
    thread_id = os.getenv("THREAD_ID", "demo-thread")
    subject = f"thread.{thread_id}.worker"
    print("Listening for COMMIT envelopes on", subject)
    await subscribe_envelopes(thread_id, subject, handle)

if __name__ == "__main__":
    asyncio.run(main())
    