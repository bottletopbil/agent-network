"""
Agent Manifest System

Defines agent capabilities, schemas, and metadata for intelligent routing.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentManifest:
    """
    Agent manifest describing capabilities, schema, and performance.
    
    This is advertised by agents to declare what they can do, allowing
    the routing system to match tasks to suitable agents.
    """
    
    # Identity
    agent_id: str
    
    # Capabilities
    capabilities: List[str]  # e.g., ["code_generation", "data_analysis"]
    
    # I/O Schema
    io_schema: Dict[str, Any]  # JSON schema for input/output
    
    # Metadata
    tags: List[str] = field(default_factory=list)  # e.g., ["python", "ml", "finance"]
    constraints: Dict[str, Any] = field(default_factory=dict)  # e.g., {"min_memory_gb": 8}
    
    # Economics
    price_per_task: float = 0.0  # Credits/tokens per task
    
    # Performance Metrics
    avg_latency_ms: float = 0.0  # Average response time
    success_rate: float = 1.0    # Success rate (0.0 - 1.0)
    
    # Availability
    zone: Optional[str] = None  # Geographic/network zone, e.g., "us-west-2"
    availability: float = 1.0   # Uptime (0.0 - 1.0)
    
    # Versioning
    version: str = "1.0.0"
    
    def matches_capability(self, capability: str) -> bool:
        """Check if agent has a specific capability"""
        return capability in self.capabilities
    
    def matches_tags(self, tags: List[str]) -> bool:
        """Check if agent has all specified tags"""
        return all(tag in self.tags for tag in tags)
    
    def matches_any_tag(self, tags: List[str]) -> bool:
        """Check if agent has any of the specified tags"""
        return any(tag in self.tags for tag in tags)
    
    def get_constraint(self, key: str, default: Any = None) -> Any:
        """Get a constraint value"""
        return self.constraints.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "io_schema": self.io_schema,
            "tags": self.tags,
            "constraints": self.constraints,
            "price_per_task": self.price_per_task,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": self.success_rate,
            "zone": self.zone,
            "availability": self.availability,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentManifest':
        """Create from dictionary"""
        return cls(**data)


class ManifestRegistry:
    """
    Registry of agent manifests for discovery and filtering.
    
    Maintains a central registry of all available agents and their
    capabilities, enabling fast lookups and filtering.
    """
    
    def __init__(self):
        self.manifests: Dict[str, AgentManifest] = {}
        self.capability_index: Dict[str, Set[str]] = {}  # capability -> agent_ids
        self.tag_index: Dict[str, Set[str]] = {}  # tag -> agent_ids
        self.zone_index: Dict[str, Set[str]] = {}  # zone -> agent_ids
    
    def register(self, manifest: AgentManifest) -> None:
        """
        Register an agent manifest.
        
        Args:
            manifest: Agent manifest to register
        """
        agent_id = manifest.agent_id
        
        # Store manifest
        self.manifests[agent_id] = manifest
        
        # Update capability index
        for capability in manifest.capabilities:
            if capability not in self.capability_index:
                self.capability_index[capability] = set()
            self.capability_index[capability].add(agent_id)
        
        # Update tag index
        for tag in manifest.tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = set()
            self.tag_index[tag].add(agent_id)
        
        # Update zone index
        if manifest.zone:
            if manifest.zone not in self.zone_index:
                self.zone_index[manifest.zone] = set()
            self.zone_index[manifest.zone].add(agent_id)
        
        logger.info(f"Registered agent {agent_id} with capabilities: {manifest.capabilities}")
    
    def unregister(self, agent_id: str) -> None:
        """
        Unregister an agent.
        
        Args:
            agent_id: ID of agent to unregister
        """
        if agent_id not in self.manifests:
            logger.warning(f"Attempted to unregister unknown agent: {agent_id}")
            return
        
        manifest = self.manifests[agent_id]
        
        # Remove from capability index
        for capability in manifest.capabilities:
            if capability in self.capability_index:
                self.capability_index[capability].discard(agent_id)
                if not self.capability_index[capability]:
                    del self.capability_index[capability]
        
        # Remove from tag index
        for tag in manifest.tags:
            if tag in self.tag_index:
                self.tag_index[tag].discard(agent_id)
                if not self.tag_index[tag]:
                    del self.tag_index[tag]
        
        # Remove from zone index
        if manifest.zone and manifest.zone in self.zone_index:
            self.zone_index[manifest.zone].discard(agent_id)
            if not self.zone_index[manifest.zone]:
                del self.zone_index[manifest.zone]
        
        # Remove manifest
        del self.manifests[agent_id]
        
        logger.info(f"Unregistered agent {agent_id}")
    
    def get(self, agent_id: str) -> Optional[AgentManifest]:
        """Get a specific agent manifest"""
        return self.manifests.get(agent_id)
    
    def find_by_capability(self, capability: str) -> List[AgentManifest]:
        """
        Find all agents with a specific capability.
        
        Args:
            capability: Capability to search for
            
        Returns:
            List of agent manifests with the capability
        """
        agent_ids = self.capability_index.get(capability, set())
        return [self.manifests[aid] for aid in agent_ids]
    
    def find_by_tags(self, tags: List[str], match_all: bool = True) -> List[AgentManifest]:
        """
        Find agents by tags.
        
        Args:
            tags: Tags to search for
            match_all: If True, agent must have all tags. If False, any tag.
            
        Returns:
            List of matching agent manifests
        """
        if not tags:
            return list(self.manifests.values())
        
        if match_all:
            # Agent must have all tags
            matching_agents = []
            for manifest in self.manifests.values():
                if manifest.matches_tags(tags):
                    matching_agents.append(manifest)
            return matching_agents
        else:
            # Agent must have at least one tag
            agent_ids = set()
            for tag in tags:
                if tag in self.tag_index:
                    agent_ids.update(self.tag_index[tag])
            return [self.manifests[aid] for aid in agent_ids]
    
    def find_by_zone(self, zone: str) -> List[AgentManifest]:
        """
        Find all agents in a specific zone.
        
        Args:
            zone: Zone to search for
            
        Returns:
            List of agent manifests in the zone
        """
        agent_ids = self.zone_index.get(zone, set())
        return [self.manifests[aid] for aid in agent_ids]
    
    def get_all(self) -> List[AgentManifest]:
        """Get all registered agent manifests"""
        return list(self.manifests.values())
    
    def count(self) -> int:
        """Get count of registered agents"""
        return len(self.manifests)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_agents": len(self.manifests),
            "capabilities": len(self.capability_index),
            "tags": len(self.tag_index),
            "zones": len(self.zone_index),
        }


# Global registry instance
_global_registry: Optional[ManifestRegistry] = None


def get_registry() -> ManifestRegistry:
    """Get or create the global manifest registry"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ManifestRegistry()
    return _global_registry


def reset_registry() -> None:
    """Reset the global registry (for testing)"""
    global _global_registry
    _global_registry = ManifestRegistry()
