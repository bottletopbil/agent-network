"""
Unit tests for Base Agent class.

Tests:
- Agent subscription to NATS
- Envelope handling callback
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import asyncio
from agent import BaseAgent
from unittest.mock import AsyncMock, patch, MagicMock


class ConcreteTestAgent(BaseAgent):
    """Concrete test implementation of BaseAgent"""

    def __init__(self, agent_id: str, public_key_b64: str):
        super().__init__(agent_id, public_key_b64)
        self.envelopes_received = []

    async def on_envelope(self, envelope: dict):
        """Track received envelopes"""
        self.envelopes_received.append(envelope)


class TestAgentSubscription:
    """Test base agent subscription capabilities"""

    @pytest.mark.asyncio
    async def test_agent_subscription(self):
        """Verify base agent can subscribe to bus"""
        agent = ConcreteTestAgent("test-agent", "test-public-key")

        # Mock subscribe_envelopes to avoid actual NATS connection
        with patch("agent.subscribe_envelopes") as mock_subscribe:
            # Make it an async mock
            mock_subscribe.return_value = AsyncMock()

            # Create a task that will be cancelled after a short time
            async def run_briefly():
                try:
                    await agent.run("test-thread", "thread.test.*")
                except Exception:
                    pass

            task = asyncio.create_task(run_briefly())

            # Give it a moment to call subscribe_envelopes
            await asyncio.sleep(0.1)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify subscribe_envelopes was called with correct parameters
            mock_subscribe.assert_called_once()
            call_args = mock_subscribe.call_args

            assert call_args[0][0] == "test-thread"
            assert call_args[0][1] == "thread.test.*"
            # Third argument should be the on_envelope method
            assert callable(call_args[0][2])


class TestAgentEnvelopeHandling:
    """Test envelope handling callback"""

    @pytest.mark.asyncio
    async def test_agent_envelope_handling(self):
        """Verify on_envelope callback is invoked"""
        agent = ConcreteTestAgent("test-agent", "test-public-key")

        # Create test envelopes
        envelope1 = {"kind": "NEED", "thread_id": "test", "payload": {"task": "test1"}}
        envelope2 = {"kind": "PROPOSE", "thread_id": "test", "payload": {"plan": []}}

        # Call on_envelope directly (as bus would do)
        await agent.on_envelope(envelope1)
        await agent.on_envelope(envelope2)

        # Verify envelopes were received
        assert len(agent.envelopes_received) == 2
        assert agent.envelopes_received[0] == envelope1
        assert agent.envelopes_received[1] == envelope2

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Verify agent initializes with correct properties"""
        agent = ConcreteTestAgent("my-agent", "my-public-key-123")

        assert agent.agent_id == "my-agent"
        assert agent.public_key_b64 == "my-public-key-123"
        assert agent.envelopes_received == []
