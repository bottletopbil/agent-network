"""
Unit tests for Verb Dispatcher and NEED Handler.

Tests:
- Dispatcher registration
- Envelope routing
- NEED handler task creation
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from verbs import VerbDispatcher, DISPATCHER
from plan_store import PlanStore, OpType
import handlers.need


class TestDispatcherRegistration:
    """Test handler registration"""

    def test_dispatcher_registration(self):
        """Verify handlers can be registered and listed"""
        dispatcher = VerbDispatcher()

        # Initial state - no handlers
        assert len(dispatcher.list_verbs()) == 0

        # Register a mock handler
        async def mock_handler(envelope):
            pass

        dispatcher.register("TEST_VERB", mock_handler)

        # Verify registration
        assert "TEST_VERB" in dispatcher.list_verbs()
        assert len(dispatcher.list_verbs()) == 1
        assert dispatcher.handlers["TEST_VERB"] == mock_handler

    def test_multiple_registrations(self):
        """Verify multiple handlers can be registered"""
        dispatcher = VerbDispatcher()

        async def handler1(envelope):
            pass

        async def handler2(envelope):
            pass

        dispatcher.register("VERB1", handler1)
        dispatcher.register("VERB2", handler2)

        assert len(dispatcher.list_verbs()) == 2
        assert "VERB1" in dispatcher.list_verbs()
        assert "VERB2" in dispatcher.list_verbs()


class TestDispatcherDispatch:
    """Test envelope routing"""

    @pytest.mark.asyncio
    async def test_dispatcher_dispatch(self):
        """Verify envelopes are routed to correct handler"""
        dispatcher = VerbDispatcher()

        # Track which handler was called
        called = {"handler": None, "envelope": None}

        async def test_handler(envelope):
            called["handler"] = "test_handler"
            called["envelope"] = envelope

        dispatcher.register("TEST_KIND", test_handler)

        # Dispatch envelope
        test_envelope = {"kind": "TEST_KIND", "payload": {"data": "test"}}
        result = await dispatcher.dispatch(test_envelope)

        # Verify handler was called
        assert result is True
        assert called["handler"] == "test_handler"
        assert called["envelope"] == test_envelope

    @pytest.mark.asyncio
    async def test_dispatch_no_handler(self):
        """Verify dispatch returns False when no handler exists"""
        dispatcher = VerbDispatcher()

        envelope = {"kind": "UNKNOWN_KIND"}
        result = await dispatcher.dispatch(envelope)

        assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_routes_correctly(self):
        """Verify dispatcher routes to correct handler based on kind"""
        dispatcher = VerbDispatcher()

        results = {"handler_a": False, "handler_b": False}

        async def handler_a(envelope):
            results["handler_a"] = True

        async def handler_b(envelope):
            results["handler_b"] = True

        dispatcher.register("KIND_A", handler_a)
        dispatcher.register("KIND_B", handler_b)

        # Dispatch to handler A
        await dispatcher.dispatch({"kind": "KIND_A"})
        assert results["handler_a"] is True
        assert results["handler_b"] is False

        # Reset and dispatch to handler B
        results["handler_a"] = False
        await dispatcher.dispatch({"kind": "KIND_B"})
        assert results["handler_a"] is False
        assert results["handler_b"] is True


class TestNeedHandler:
    """Test NEED handler task creation"""

    @pytest.mark.asyncio
    async def test_need_handler(self):
        """Verify NEED handler creates tasks in plan store"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)

        # Inject plan store into need handler
        handlers.need.plan_store = store

        # Create NEED envelope
        envelope = {
            "kind": "NEED",
            "thread_id": "test-thread",
            "lamport": 10,
            "sender_pk_b64": "alice-public-key",
            "payload": {
                "task_type": "classify",
                "requires": ["input.txt"],
                "produces": ["output.json"],
            },
        }

        # Handle NEED
        await handlers.need.handle_need(envelope)

        # Verify task was created
        ops = store.get_ops_for_thread("test-thread")
        assert len(ops) == 1

        op = ops[0]
        assert op.op_type == OpType.ADD_TASK
        assert op.thread_id == "test-thread"
        assert op.lamport == 10
        assert op.actor_id == "alice-public-key"
        assert op.payload["type"] == "classify"
        assert op.payload["requires"] == ["input.txt"]
        assert op.payload["produces"] == ["output.json"]

        # Verify task is in derived view
        task = store.get_task(op.task_id)
        assert task is not None
        assert task["task_type"] == "classify"
        assert task["state"] == "DRAFT"

    def test_need_registered_with_dispatcher(self):
        """Verify NEED handler is registered with global dispatcher"""
        # The import of handlers.need should have registered NEED
        assert "NEED" in DISPATCHER.list_verbs()
        assert DISPATCHER.handlers["NEED"] == handlers.need.handle_need

    @pytest.mark.asyncio
    async def test_need_default_task_type(self):
        """Verify NEED handler uses default task_type if not provided"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.need.plan_store = store

        envelope = {
            "kind": "NEED",
            "thread_id": "test-thread-2",
            "lamport": 5,
            "sender_pk_b64": "bob-key",
            "payload": {},  # No task_type
        }

        await handlers.need.handle_need(envelope)

        ops = store.get_ops_for_thread("test-thread-2")
        assert len(ops) == 1
        assert ops[0].payload["type"] == "generic"  # Default
        assert ops[0].payload["requires"] == []  # Default
        assert ops[0].payload["produces"] == []  # Default
