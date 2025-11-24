"""
Publish a test NEED message.

Simple helper script for demos and testing.
"""

import asyncio
import os
import uuid
import base64
import sys

sys.path.append("src")
from bus import publish_envelope
from envelope import make_envelope, sign_envelope
from crypto import load_verifier

async def main():
    thread_id = os.getenv("THREAD_ID", str(uuid.uuid4()))
    subject = f"thread.{thread_id}.need"

    # Sender public key for the envelope
    sender_pk_b64 = base64.b64encode(bytes(load_verifier())).decode()

    # Test payload
    payload = {"task": "classify", "data": "sample input"}
    
    env = make_envelope(
        kind="NEED",
        thread_id=thread_id,
        sender_pk_b64=sender_pk_b64,
        payload=payload,
    )
    signed = sign_envelope(env)
    await publish_envelope(thread_id, subject, signed)
    
    print(f"✓ Published NEED to {subject}")
    print(f"  Thread ID: {thread_id}")
    print(f"  Payload: {payload}")

if __name__ == "__main__":
    asyncio.run(main())
