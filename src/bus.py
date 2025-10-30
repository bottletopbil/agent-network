import asyncio, os, json
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from typing import Callable, Awaitable
from audit import log_event
from envelope import verify_envelope, observe_envelope  # NEW


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
    High-level: publish a SIGNED ENVELOPE only if it verifies locally.
    """
    if not verify_envelope(envelope):
        raise ValueError("Refusing to publish: envelope failed local verification")
    await publish_raw(thread_id, subject, envelope)

async def subscribe_envelopes(thread_id: str, subject: str,
                              handler: Callable[[dict], Awaitable[None]]):
    """
    Subscribe and ONLY deliver verified envelopes to handler.
    """
    nc, js = await connect()
    durable = subject.replace(".", "_")
    sub = await js.subscribe(subject, durable=durable)

    async def _runner():
        async for msg in sub.messages:
            try:
                env = json.loads(msg.data.decode())
            except Exception:
                env = {"_raw": msg.data.decode(errors="ignore")}
                log_event(thread_id=thread_id, subject=subject, kind="BUS.DELIVER", payload=env)
                await msg.term()  # drop malformed
                continue

            # Always log delivery (CCTV)
            log_event(thread_id=thread_id, subject=subject, kind="BUS.DELIVER", payload=env)

            # Verify envelope signature & payload hash
            if not verify_envelope(env):
                await msg.term()
                continue

            # Update our lamport clock from the message
            observe_envelope(env)

            await handler(env)
            await msg.ack()

    try:
        await _runner()
    finally:
        await nc.drain()