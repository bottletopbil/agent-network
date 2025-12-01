"""Agent manifest registry for discovery and lookup.

Provides in-memory registry for agent manifests with capability-based
search and agent lookup.
"""

import logging
from typing import List, Optional, Dict
from collections import defaultdict

from .manifest import AgentManifest

logger = logging.getLogger(__name__)


class ManifestRegistry:
    """
    Registry for agent manifests.

    Provides:
    - Manifest registration and storage
    - Capability-based search
    - Agent lookup by DID
    """

    def __init__(self):
        """Initialize manifest registry."""
        # Map agent_id -> manifest
        self.manifests: Dict[str, AgentManifest] = {}

        # Index: capability -> [agent_ids]
        self.capability_index: Dict[str, List[str]] = defaultdict(list)

        # Index: tag -> [agent_ids]
        self.tag_index: Dict[str, List[str]] = defaultdict(list)

    def register(self, manifest: AgentManifest) -> bool:
        """
        Register an agent manifest.

        Args:
            manifest: Manifest to register

        Returns:
            True if registered successfully
        """
        agent_id = manifest.agent_id

        # Check if already registered
        if agent_id in self.manifests:
            logger.info(f"Updating manifest for agent {agent_id[:30]}...")
            # Remove old indices
            self._remove_from_indices(agent_id)

        # Store manifest
        self.manifests[agent_id] = manifest

        # Index by capabilities
        for capability in manifest.capabilities:
            if agent_id not in self.capability_index[capability]:
                self.capability_index[capability].append(agent_id)

        # Index by tags
        for tag in manifest.tags:
            if agent_id not in self.tag_index[tag]:
                self.tag_index[tag].append(agent_id)

        logger.info(
            f"Registered manifest: {agent_id[:30]}... "
            f"({len(manifest.capabilities)} capabilities, {len(manifest.tags)} tags)"
        )

        return True

    def _remove_from_indices(self, agent_id: str):
        """Remove agent from all indices."""
        # Remove from capability index
        for capability, agents in list(self.capability_index.items()):
            if agent_id in agents:
                agents.remove(agent_id)
                if not agents:
                    del self.capability_index[capability]

        # Remove from tag index
        for tag, agents in list(self.tag_index.items()):
            if agent_id in agents:
                agents.remove(agent_id)
                if not agents:
                    del self.tag_index[tag]

    def find_by_capability(self, capability: str) -> List[AgentManifest]:
        """
        Find agents with a specific capability.

        Args:
            capability: Capability to search for

        Returns:
            List of matching manifests
        """
        agent_ids = self.capability_index.get(capability, [])
        manifests = [self.manifests[aid] for aid in agent_ids]

        logger.debug(f"Found {len(manifests)} agents with capability '{capability}'")

        return manifests

    def find_by_tag(self, tag: str) -> List[AgentManifest]:
        """
        Find agents with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of matching manifests
        """
        agent_ids = self.tag_index.get(tag, [])
        manifests = [self.manifests[aid] for aid in agent_ids]

        logger.debug(f"Found {len(manifests)} agents with tag '{tag}'")

        return manifests

    def get_manifest(self, agent_id: str) -> Optional[AgentManifest]:
        """
        Get manifest for a specific agent.

        Args:
            agent_id: Agent's DID

        Returns:
            Manifest if found, None otherwise
        """
        manifest = self.manifests.get(agent_id)

        if manifest:
            logger.debug(f"Retrieved manifest for {agent_id[:30]}...")
        else:
            logger.debug(f"No manifest found for {agent_id[:30]}...")

        return manifest

    def unregister(self, agent_id: str) -> bool:
        """
        Remove an agent from the registry.

        Args:
            agent_id: Agent's DID

        Returns:
            True if removed successfully
        """
        if agent_id not in self.manifests:
            logger.warning(f"Agent not registered: {agent_id[:30]}...")
            return False

        # Remove from indices
        self._remove_from_indices(agent_id)

        # Remove manifest
        del self.manifests[agent_id]

        logger.info(f"Unregistered agent {agent_id[:30]}...")

        return True

    def list_all(self) -> List[AgentManifest]:
        """
        List all registered manifests.

        Returns:
            List of all manifests
        """
        return list(self.manifests.values())

    def count(self) -> int:
        """
        Get count of registered agents.

        Returns:
            Number of registered agents
        """
        return len(self.manifests)

    def search(
        self,
        capabilities: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        max_price: Optional[float] = None,
        max_latency: Optional[int] = None,
    ) -> List[AgentManifest]:
        """
        Advanced search for agents.

        Args:
            capabilities: Required capabilities (AND logic)
            tags: Required tags (AND logic)
            max_price: Maximum price per task
            max_latency: Maximum latency in ms

        Returns:
            List of matching manifests
        """
        results = list(self.manifests.values())

        # Filter by capabilities
        if capabilities:
            results = [m for m in results if all(cap in m.capabilities for cap in capabilities)]

        # Filter by tags
        if tags:
            results = [m for m in results if all(tag in m.tags for tag in tags)]

        # Filter by price
        if max_price is not None:
            results = [m for m in results if m.price_per_task <= max_price]

        # Filter by latency
        if max_latency is not None:
            results = [m for m in results if m.avg_latency_ms <= max_latency]

        logger.info(
            f"Search returned {len(results)} manifests "
            f"(caps={capabilities}, tags={tags}, "
            f"max_price={max_price}, max_latency={max_latency})"
        )

        return results

    def get_capabilities(self) -> List[str]:
        """
        Get all registered capabilities.

        Returns:
            List of unique capabilities
        """
        return list(self.capability_index.keys())

    def get_tags(self) -> List[str]:
        """
        Get all registered tags.

        Returns:
            List of unique tags
        """
        return list(self.tag_index.keys())
