"""
Verb Dispatcher: routes envelopes to handlers based on kind.
"""

from typing import Dict, Callable, Awaitable, Any
from dataclasses import dataclass
import asyncio

VerbHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class VerbDispatcher:
    def __init__(self):
        self.handlers: Dict[str, VerbHandler] = {}

    def register(self, kind: str, handler: VerbHandler):
        """Register a handler for a verb kind"""
        self.handlers[kind] = handler

    async def dispatch(self, envelope: Dict[str, Any]) -> bool:
        """
        Dispatch envelope to registered handler.
        Returns True if handled, False if no handler.
        """
        kind = envelope.get("kind")
        handler = self.handlers.get(kind)

        if handler is None:
            return False

        await handler(envelope)
        return True

    def list_verbs(self) -> list:
        """List all registered verbs"""
        return list(self.handlers.keys())


# Global dispatcher instance
DISPATCHER = VerbDispatcher()
