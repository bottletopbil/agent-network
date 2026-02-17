import asyncio, os, json
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from typing import Callable, Awaitable
import logging

from audit import log_event
from envelope import observe_envelope

from policy import validate_envelope  # Rule book v0 compatibility gate
from policy.gates import GateEnforcer

# Backward compatibility: allow importing `bus.*` submodules while this file remains a module.
__path__ = [os.path.dirname(__file__)]

# OpenTelemetry tracing
try:
    from observability.tracing import (
        create_span,
        propagate_context,
        start_span_from_context,
    )
    from opentelemetry.trace import SpanKind

    TRACING_ENABLED = True
except ImportError:
    TRACING_ENABLED = False

logger = logging.getLogger(__name__)

# Global gate enforcer instance
_gate_enforcer = None


def get_gate_enforcer() -> GateEnforcer:
    """Get or create the global gate enforcer"""
    global _gate_enforcer
    if _gate_enforcer is None:
        _gate_enforcer = GateEnforcer()
    return _gate_enforcer


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


class ConnectionPool:
    """
    Connection pool for NATS connections.

    Maintains a pool of reusable connections to avoid overhead
    of creating new connections for each publish.
    """

    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self._pool: list[tuple[NATS, JetStreamContext]] = []
        self._in_use: set[tuple[NATS, JetStreamContext]] = set()
        self._lock = asyncio.Lock()

    async def get(self) -> tuple[NATS, JetStreamContext]:
        """Get a connection from the pool."""
        async with self._lock:
            # Try to reuse existing connection
            if self._pool:
                conn = self._pool.pop()
                self._in_use.add(conn)
                return conn

            # Create new if under limit
            if len(self._in_use) < self.max_size:
                conn = await connect()
                self._in_use.add(conn)
                return conn

            # Wait and retry if at limit
            # (In production, might want to wait for release or raise)
            await asyncio.sleep(0.01)
            return await self.get()

    async def release(self, conn: tuple[NATS, JetStreamContext]):
        """Return a connection to the pool."""
        async with self._lock:
            if conn in self._in_use:
                self._in_use.remove(conn)
                self._pool.append(conn)

    async def close_all(self):
        """Close all connections in the pool."""
        async with self._lock:
            # Close all pooled connections
            for nc, _ in self._pool:
                try:
                    await nc.drain()
                except Exception:
                    pass

            # Close all in-use connections
            for nc, _ in self._in_use:
                try:
                    await nc.drain()
                except Exception:
                    pass

            self._pool.clear()
            self._in_use.clear()


# Global connection pool
_connection_pool = ConnectionPool(max_size=10)


async def publish_raw(thread_id: str, subject: str, message: dict):
    """
    Kept for low-level use; still logs BUS.PUBLISH.

    Now uses connection pooling for better performance.
    """
    nc, js = await _connection_pool.get()
    try:
        data = json.dumps(message).encode()
        await js.publish(subject, data)
        log_event(thread_id=thread_id, subject=subject, kind="BUS.PUBLISH", payload=message)
    finally:
        # Return connection to pool instead of draining
        await _connection_pool.release((nc, js))


async def publish(thread_id: str, subject: str, message: dict):
    """
    Backward-compatible wrapper: publish a simple message (not an envelope).
    Logs to audit trail but does NOT validate as an envelope.
    """
    await publish_raw(thread_id, subject, message)


async def publish_envelope(thread_id: str, subject: str, envelope: dict):
    """
    High-level: publish a SIGNED ENVELOPE only if it passes the rule book locally.
    Now includes PREFLIGHT gate validation and distributed tracing.
    """
    # Create span for publish operation
    if TRACING_ENABLED:
        with create_span(
            "bus.publish_envelope",
            attributes={
                "thread_id": thread_id,
                "subject": subject,
                "operation": envelope.get("operation", "unknown"),
            },
            kind=SpanKind.PRODUCER,
        ):
            # ✅ Original policy check (sig/lamport/payload/CAS)
            validate_envelope(envelope)

            # ✅ PREFLIGHT gate: Fast check before publishing
            gate_enforcer = get_gate_enforcer()
            decision = gate_enforcer.preflight_validate(envelope)
            if not decision.allowed:
                logger.error(f"Preflight validation failed: {decision.reason}")
                raise ValueError(f"Preflight validation failed: {decision.reason}")

            # Inject trace context into envelope
            propagate_context(envelope)

            logger.debug(f"Preflight passed for {envelope.get('operation')}")
            await publish_raw(thread_id, subject, envelope)
    else:
        # No tracing available
        validate_envelope(envelope)
        gate_enforcer = get_gate_enforcer()
        decision = gate_enforcer.preflight_validate(envelope)
        if not decision.allowed:
            logger.error(f"Preflight validation failed: {decision.reason}")
            raise ValueError(f"Preflight validation failed: {decision.reason}")
        logger.debug(f"Preflight passed for {envelope.get('operation')}")
        await publish_raw(thread_id, subject, envelope)


async def subscribe_envelopes(
    thread_id: str,
    subject: str,
    handler: Callable[[dict], Awaitable[None]],
    durable_name: str = None,
):
    """
    Subscribe and ONLY deliver envelopes that pass the rule book to your handler.
    """
    nc, js = await connect()
    durable = durable_name or subject.replace(".", "_").replace("*", "ALL").replace(">", "ALL")
    sub = await js.subscribe(subject, durable=durable)

    async def _runner():
        async for msg in sub.messages:
            # Decode (malformed messages are dropped but still logged)
            try:
                env = json.loads(msg.data.decode())
            except Exception:
                env = {"_raw": msg.data.decode(errors="ignore")}
                log_event(
                    thread_id=thread_id,
                    subject=subject,
                    kind="BUS.DELIVER",
                    payload=env,
                )
                await msg.term()  # drop malformed
                continue

            # Always log delivery (CCTV)
            log_event(thread_id=thread_id, subject=subject, kind="BUS.DELIVER", payload=env)

            # ✅ Verify via policy (defense in depth on receive)
            try:
                validate_envelope(env)
            except Exception as e:
                logger.warning(f"Envelope validation failed: {e}")
                await msg.term()
                continue

            # ✅ INGRESS gate: Full WASM evaluation on receive
            gate_enforcer = get_gate_enforcer()
            decision = gate_enforcer.ingress_validate(env)
            if not decision.allowed:
                logger.warning(f"Ingress validation failed: {decision.reason}")
                await msg.term()
                continue

            logger.debug(f"Ingress passed for {env.get('operation')}")

            # Update local Lamport clock from the verified envelope
            observe_envelope(env)

            # Extract trace context and continue distributed trace
            if TRACING_ENABLED:
                with start_span_from_context(
                    "bus.handle_envelope",
                    env,
                    attributes={
                        "thread_id": thread_id,
                        "subject": subject,
                        "operation": env.get("operation", "unknown"),
                    },
                    kind=SpanKind.CONSUMER,
                ):
                    await handler(env)
            else:
                await handler(env)

            await msg.ack()

    try:
        await _runner()
    finally:
        await nc.drain()


async def subscribe(
    thread_id: str,
    subject: str,
    handler: Callable[[dict], Awaitable[None]],
    durable_name: str = None,
):
    """
    Backward-compatible wrapper: subscribe to simple messages (not envelopes).
    Logs to audit trail but does NOT validate as envelopes.
    """
    nc, js = await connect()
    durable = durable_name or subject.replace(".", "_").replace("*", "ALL").replace(">", "ALL")
    sub = await js.subscribe(subject, durable=durable)

    async def _runner():
        async for msg in sub.messages:
            # Decode message
            try:
                payload = json.loads(msg.data.decode())
            except Exception:
                payload = {"_raw": msg.data.decode(errors="ignore")}

            # Always log delivery (CCTV)
            log_event(
                thread_id=thread_id,
                subject=subject,
                kind="BUS.DELIVER",
                payload=payload,
            )

            # Call handler (no envelope validation)
            await handler(payload)
            await msg.ack()

    try:
        await _runner()
    finally:
        await nc.drain()


class P2PBus:
    """
    P2P Bus using Gossipsub for envelope transport.

    Alternative to NATSBus using libp2p gossipsub protocol.
    """

    def __init__(self, p2p_node=None, gossipsub_router=None):
        """Initialize P2P bus"""
        self.p2p_node = p2p_node

        if gossipsub_router is None:
            from p2p.gossipsub import GossipsubRouter

            self.gossipsub = GossipsubRouter(p2p_node)
        else:
            self.gossipsub = gossipsub_router

        logger.info("P2P bus initialized with gossipsub")

    def publish_envelope(self, envelope, subject):
        """Publish envelope via gossipsub"""
        from p2p.topics import create_thread_topic

        parts = subject.split(".")
        if len(parts) >= 2:
            thread_id, verb = parts[0], parts[1]
        else:
            thread_id = subject
            verb = envelope.get("kind", "unknown").lower()

        topic = create_thread_topic(thread_id, verb)
        envelope_bytes = json.dumps(envelope, sort_keys=True).encode("utf-8")
        self.gossipsub.publish(topic, envelope_bytes)
        logger.debug(f"Published envelope to P2P topic: {topic}")

    def subscribe_envelopes(self, subject, handler):
        """Subscribe to envelopes via gossipsub"""
        from p2p.topics import create_thread_topic

        parts = subject.split(".")
        if len(parts) >= 2:
            thread_id, verb = parts[0], parts[1]
        else:
            thread_id, verb = subject, "*"

        topic = create_thread_topic(thread_id, verb)

        def gossipsub_handler(message_bytes):
            try:
                envelope = json.loads(message_bytes.decode("utf-8"))
                handler(envelope)
            except Exception as e:
                logger.error(f"Error in P2P subscriber: {e}")

        self.gossipsub.subscribe(topic, gossipsub_handler)
        logger.info(f"Subscribed to P2P topic: {topic}")

    def get_stats(self):
        """Get bus statistics"""
        return self.gossipsub.get_stats()


def get_bus():
    """
    Get bus instance based on environment configuration.

    Returns:
        Bus instance (HybridBus, P2PBus, or NATSBus)
    """
    import os

    p2p_enabled = os.getenv("P2P_ENABLED", "false").lower() == "true"

    if p2p_enabled:
        # Use hybrid bus
        from bus.hybrid import HybridBus

        logger.info("Using hybrid NATS+P2P bus")
        return HybridBus()
    else:
        # Use P2PBus as default (NATS requires async)
        logger.info("Using P2P bus")
        return P2PBus()
