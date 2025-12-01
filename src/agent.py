"""
Base Agent: common functionality for all agent types.
"""

import asyncio
from abc import ABC, abstractmethod
from bus import subscribe_envelopes
from verbs import DISPATCHER


class BaseAgent(ABC):
    def __init__(self, agent_id: str, public_key_b64: str):
        self.agent_id = agent_id
        self.public_key_b64 = public_key_b64

    @abstractmethod
    async def on_envelope(self, envelope: dict):
        """Override to handle incoming envelopes"""
        pass

    async def run(self, thread_id: str, subject: str):
        """Main agent loop"""
        print(f"[{self.agent_id}] Starting on {subject}")
        # Create unique durable name for this agent
        safe_subject = subject.replace(".", "_").replace("*", "ALL").replace(">", "ALL")
        durable = f"{self.agent_id}_{safe_subject}"
        await subscribe_envelopes(
            thread_id, subject, self.on_envelope, durable_name=durable
        )
