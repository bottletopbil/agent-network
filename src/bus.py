import asyncio, os, json
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from typing import Callable, Awaitable

from audit import log_event
from envelope import observe_envelope
from policy import validate_envelope  # ✅ Rule book v0 gate

NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
STREAM = os.getenv("SWARM_STREAM", "THREADS")
SUBJECTS = os.getenv("SWARM_SUBJECTS", "thread.*.*")  # e.g. thread.{threadId}.{role}

async def _ensure_stream(js: JetStreamContext):
    streams = await js.streams_info()
    names = {s.config.name for s in streams}
    if STREAM not in names:
        await js.add_stream(name=STREAM, subjects=[SUBJECTS])

async def connect() -> tuple[NATS, JetStreamContext]:
    nc = NATS()
    await nc.connect(servers=[NATS_URL])
    js = nc.jetstream()
    await _ensure_stream(js)
    return nc, js

async def publish_raw(thread_id: str, subject: str, message: dict):
    """
    Kept for low-level use; still logs BUS.PUBLISH.
    """
    nc, js = await connect()
    try:
        data = json.dumps(message).encode()
        await js.publish(subject, data)
        log_event(thread_id=thread_id, subject=subject, kind="BUS.PUBLISH", payload=message)
    finally:
        await nc.drain()

async def publish_envelope(thread_id: str, subject: str, envelope: dict):
    """
    High-level: publish a SIGNED ENVELOPE only if it passes the rule book locally.
    """
    # ✅ Policy check BEFORE putting on the wire (includes sig/lamport/payload/CAS)
    validate_envelope(envelope)
    await publish_raw(thread_id, subject, envelope)

async def subscribe_envelopes(
    thread_id: str,
    subject: str,
    handler: Callable[[dict], Awaitable[None]]
):
    """
    Subscribe and ONLY deliver envelopes that pass the rule book to your handler.
    """
    nc, js = await connect()
    durable = subject.replace(".", "_")
    sub = await js.subscribe(subject, durable=durable)

    async def _runner():
        async for msg in sub.messages:
            # Decode (malformed messages are dropped but still logged)
            try:
                env = json.loads(msg.data.decode())
            except Exception:
                env = {"_raw": msg.data.decode(errors="ignore")}
                log_event(thread_id=thread_id, subject=subject, kind="BUS.DELIVER", payload=env)
                await msg.term()  # drop malformed
                continue

            # Always log delivery (CCTV)
            log_event(thread_id=thread_id, subject=subject, kind="BUS.DELIVER", payload=env)

            # ✅ Verify via policy (defense in depth on receive)
            try:
                validate_envelope(env)
            except Exception:
                await msg.term()
                continue

            # Update local Lamport clock from the verified envelope
            observe_envelope(env)

            await handler(env)
            await msg.ack()

    try:
        await _runner()
    finally:
        await nc.drain()
