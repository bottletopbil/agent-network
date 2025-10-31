import asyncio, os, uuid, base64, sys
sys.path.append("src")
from crypto import load_verifier
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from cas import put_json
from policy import current_policy_hash

async def main():
    thread_id = os.getenv("THREAD_ID", str(uuid.uuid4()))
    subject = f"thread.{thread_id}.worker"
    sender_pk_b64 = base64.b64encode(bytes(load_verifier())).decode()

    artifact = {"ok": True, "msg": "policy-demo"}
    h = put_json(artifact)

    env = make_envelope(
        kind="COMMIT",
        thread_id=thread_id,
        sender_pk_b64=sender_pk_b64,
        payload={"artifact_hash": h, "artifact_kind": "demo"},
        policy_engine_hash=current_policy_hash(),
    )
    signed = sign_envelope(env)
    await publish_envelope(thread_id, subject, signed)
    print("Published COMMIT with policy hash", current_policy_hash())

if __name__ == "__main__":
    asyncio.run(main())
