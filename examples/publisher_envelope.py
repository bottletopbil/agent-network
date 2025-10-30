import asyncio, os, uuid, base64, sys
sys.path.append("src")
from bus import publish_envelope
from envelope import make_envelope, sign_envelope
from crypto import load_verifier

async def main():
    thread_id = os.getenv("THREAD_ID", str(uuid.uuid4()))
    subject = f"thread.{thread_id}.planner"

    # Sender public key for the envelope (who am I?)
    sender_pk_b64 = base64.b64encode(bytes(load_verifier())).decode()

    payload = {"hello": "swarm", "n": 2}
    env = make_envelope(
        kind="NEED",
        thread_id=thread_id,
        sender_pk_b64=sender_pk_b64,
        payload=payload,
        policy_engine_hash="v0",
    )
    signed = sign_envelope(env)
    await publish_envelope(thread_id, subject, signed)
    print("Published signed envelope to", subject)

if __name__ == "__main__":
    asyncio.run(main())
