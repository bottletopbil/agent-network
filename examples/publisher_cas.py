import asyncio, os, uuid, base64, sys
sys.path.append("src")
from crypto import load_verifier
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from cas import put_json

async def main():
    thread_id = os.getenv("THREAD_ID", str(uuid.uuid4()))
    subject = f"thread.{thread_id}.worker"
    sender_pk_b64 = base64.b64encode(bytes(load_verifier())).decode()

    # Imagine this came from an AI model:
    artifact = {
        "labels": ["wood", "metal", "other", "wood", "wood"],
        "summary": "Mostly wood; 1 metal; 1 other."
    }
    artifact_hash = put_json(artifact)

    payload = {
        "artifact_hash": artifact_hash,
        "artifact_kind": "classification_v1",
        "algo": "sha256"
    }

    env = make_envelope(
        kind="COMMIT",
        thread_id=thread_id,
        sender_pk_b64=sender_pk_b64,
        payload=payload,
        policy_engine_hash="v0",
    )
    signed = sign_envelope(env)
    await publish_envelope(thread_id, subject, signed)
    print("Published envelope with artifact_hash:", artifact_hash)

if __name__ == "__main__":
    asyncio.run(main())
