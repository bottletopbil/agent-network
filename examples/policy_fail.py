import asyncio, os, uuid, base64, sys
sys.path.append("src")
from crypto import load_verifier
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from policy import current_policy_hash

async def main():
    thread_id = os.getenv("THREAD_ID", str(uuid.uuid4()))
    subject = f"thread.{thread_id}.worker"
    sender_pk_b64 = base64.b64encode(bytes(load_verifier())).decode()

    # Intentionally violate: COMMIT without artifact_hash
    env = make_envelope(
        kind="COMMIT",
        thread_id=thread_id,
        sender_pk_b64=sender_pk_b64,
        payload={"note": "missing artifact"},
        policy_engine_hash=current_policy_hash(),
    )
    signed = sign_envelope(env)
    try:
        await publish_envelope(thread_id, subject, signed)
    except Exception as e:
        print("Expected policy rejection:", e)

if __name__ == "__main__":
    asyncio.run(main())
