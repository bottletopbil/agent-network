"""
Chaos Nemeses: Failure Injection Primitives

Provides various failure modes for chaos testing:
- Network partitions
- Message delays
- Agent crashes
- Clock skew
"""

import time
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NemesisType(Enum):
    """Types of chaos nemeses"""
    PARTITION = "partition"
    SLOW = "slow"
    KILL = "kill"
    CLOCK_SKEW = "clock_skew"


@dataclass
class NemesisEvent:
    """Record of a nemesis action"""
    nemesis_type: NemesisType
    timestamp: float
    description: str
    affected_agents: List[str]
    metadata: Dict[str, Any]


class Nemesis(ABC):
    """
    Base class for chaos nemeses.
    
    A nemesis injects a specific type of failure into the system.
    """
    
    def __init__(self, name: str, probability: float = 0.1):
        """
        Initialize nemesis.
        
        Args:
            name: Nemesis name
            probability: Probability of activation (0.0-1.0)
        """
        self.name = name
        self.probability = probability
        self.events: List[NemesisEvent] = []
        self.active = False
    
    @abstractmethod
    def inject(self, context: Dict[str, Any]) -> bool:
        """
        Inject failure into the system.
        
        Args:
            context: Execution context (agents, messages, etc.)
        
        Returns:
            True if injection succeeded
        """
        pass
    
    @abstractmethod
    def heal(self, context: Dict[str, Any]) -> bool:
        """
        Heal the failure (restore normal operation).
        
        Args:
            context: Execution context
        
        Returns:
            True if healing succeeded
        """
        pass
    
    def should_activate(self) -> bool:
        """Determine if nemesis should activate"""
        return random.random() < self.probability
    
    def record_event(self, description: str, affected_agents: List[str], metadata: Dict[str, Any] = None):
        """Record a nemesis event"""
        event = NemesisEvent(
            nemesis_type=NemesisType[self.name.upper()] if self.name.upper() in NemesisType.__members__ else NemesisType.PARTITION,
            timestamp=time.time(),
            description=description,
            affected_agents=affected_agents,
            metadata=metadata or {}
        )
        self.events.append(event)
        logger.info(f"[{self.name}] {description}")


class PartitionNemesis(Nemesis):
    """
    Network partition nemesis.
    
    Splits the network into isolated groups that cannot communicate.
    """
    
    def __init__(self, probability: float = 0.1, partition_size: int = 2):
        """
        Initialize partition nemesis.
        
        Args:
            probability: Probability of creating partition
            partition_size: Number of partitions to create
        """
        super().__init__("partition", probability)
        self.partition_size = partition_size
        self.partitions: List[Set[str]] = []
    
    def inject(self, context: Dict[str, Any]) -> bool:
        """
        Create network partition.
        
        Splits agents into N isolated groups.
        """
        agents = context.get("agents", [])
        if len(agents) < 2:
            return False
        
        # Split agents into partitions
        shuffled = list(agents)
        random.shuffle(shuffled)
        
        partition_size = max(1, len(shuffled) // self.partition_size)
        self.partitions = []
        
        for i in range(0, len(shuffled), partition_size):
            partition = set(shuffled[i:i+partition_size])
            self.partitions.append(partition)
        
        # Record event
        affected = [agent for partition in self.partitions for agent in partition]
        self.record_event(
            f"Created {len(self.partitions)} network partitions",
            affected,
            {"partitions": [list(p) for p in self.partitions]}
        )
        
        # Install message filter in context
        context["message_filter"] = self._partition_filter
        self.active = True
        
        return True
    
    def heal(self, context: Dict[str, Any]) -> bool:
        """Heal network partition"""
        if not self.active:
            return False
        
        self.partitions = []
        if "message_filter" in context:
            del context["message_filter"]
        
        self.record_event("Healed network partition", [])
        self.active = False
        
        return True
    
    def _partition_filter(self, sender: str, receiver: str) -> bool:
        """
        Filter messages based on partition membership.
        
        Returns True if message should be delivered.
        """
        # Find sender and receiver partitions
        sender_partition = None
        receiver_partition = None
        
        for partition in self.partitions:
            if sender in partition:
                sender_partition = partition
            if receiver in partition:
                receiver_partition = partition
        
        # Only deliver if in same partition
        return sender_partition == receiver_partition and sender_partition is not None


class SlowNemesis(Nemesis):
    """
    Message delay nemesis.
    
    Introduces random delays to message delivery.
    """
    
    def __init__(self, probability: float = 0.2, delay_ms: int = 100):
        """
        Initialize slow nemesis.
        
        Args:
            probability: Probability of delaying a message
            delay_ms: Delay in milliseconds
        """
        super().__init__("slow", probability)
        self.delay_ms = delay_ms
        self.delayed_messages: List[Dict[str, Any]] = []
    
    def inject(self, context: Dict[str, Any]) -> bool:
        """
        Start delaying messages.
        
        Introduces random delays to simulate slow network.
        """
        # Install delay interceptor
        context["message_interceptor"] = self._delay_message
        
        self.record_event(
            f"Started delaying messages by {self.delay_ms}ms",
            [],
            {"delay_ms": self.delay_ms}
        )
        
        self.active = True
        return True
    
    def heal(self, context: Dict[str, Any]) -> bool:
        """Stop delaying messages"""
        if not self.active:
            return False
        
        if "message_interceptor" in context:
            del context["message_interceptor"]
        
        self.record_event("Stopped delaying messages", [])
        self.active = False
        
        return True
    
    def _delay_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delay a message.
        
        Adds random delay to message delivery.
        """
        if random.random() < self.probability:
            delay_sec = self.delay_ms / 1000.0
            time.sleep(delay_sec)
            
            if "metadata" not in message:
                message["metadata"] = {}
            message["metadata"]["chaos_delay_ms"] = self.delay_ms
        
        return message


class KillNemesis(Nemesis):
    """
    Agent crash nemesis.
    
    Randomly kills agents to test fault tolerance.
    """
    
    def __init__(self, probability: float = 0.05, kill_count: int = 1):
        """
        Initialize kill nemesis.
        
        Args:
            probability: Probability of killing agents
            kill_count: Number of agents to kill
        """
        super().__init__("kill", probability)
        self.kill_count = kill_count
        self.killed_agents: Set[str] = set()
    
    def inject(self, context: Dict[str, Any]) -> bool:
        """
        Kill random agents.
        
        Simulates agent crashes.
        """
        agents = context.get("agents", [])
        if len(agents) == 0:
            return False
        
        # Select victims
        victims = random.sample(agents, min(self.kill_count, len(agents)))
        self.killed_agents.update(victims)
        
        # Mark agents as killed in context
        if "killed_agents" not in context:
            context["killed_agents"] = set()
        context["killed_agents"].update(victims)
        
        self.record_event(
            f"Killed {len(victims)} agent(s)",
            victims,
            {"kill_count": len(victims)}
        )
        
        self.active = True
        return True
    
    def heal(self, context: Dict[str, Any]) -> bool:
        """
        Resurrect killed agents.
        
        Simulates agent recovery/restart.
        """
        if not self.active or not self.killed_agents:
            return False
        
        # Resurrect agents
        if "killed_agents" in context:
            context["killed_agents"] -= self.killed_agents
        
        resurrected = list(self.killed_agents)
        self.killed_agents.clear()
        
        self.record_event(
            f"Resurrected {len(resurrected)} agent(s)",
            resurrected
        )
        
        self.active = False
        return True


class ClockSkewNemesis(Nemesis):
    """
    Clock skew nemesis.
    
    Introduces time drift between agents.
    """
    
    def __init__(self, probability: float = 0.1, skew_ms: int = 100):
        """
        Initialize clock skew nemesis.
        
        Args:
            probability: Probability of introducing skew
            skew_ms: Maximum clock skew in milliseconds
        """
        super().__init__("clock_skew", probability)
        self.skew_ms = skew_ms
        self.agent_skews: Dict[str, int] = {}
    
    def inject(self, context: Dict[str, Any]) -> bool:
        """
        Introduce clock skew.
        
        Assigns random time offsets to each agent.
        """
        agents = context.get("agents", [])
        if not agents:
            return False
        
        # Assign random skew to each agent
        for agent in agents:
            skew = random.randint(-self.skew_ms, self.skew_ms)
            self.agent_skews[agent] = skew
        
        # Install time interceptor
        context["time_interceptor"] = self._skew_time
        
        self.record_event(
            f"Introduced clock skew (±{self.skew_ms}ms)",
            agents,
            {"skew_range_ms": self.skew_ms}
        )
        
        self.active = True
        return True
    
    def heal(self, context: Dict[str, Any]) -> bool:
        """Remove clock skew"""
        if not self.active:
            return False
        
        self.agent_skews.clear()
        
        if "time_interceptor" in context:
            del context["time_interceptor"]
        
        self.record_event("Removed clock skew", [])
        self.active = False
        
        return True
    
    def _skew_time(self, agent_id: str, timestamp_ns: int) -> int:
        """
        Apply clock skew to timestamp.
        
        Args:
            agent_id: Agent ID
            timestamp_ns: Original timestamp in nanoseconds
        
        Returns:
            Skewed timestamp
        """
        skew_ms = self.agent_skews.get(agent_id, 0)
        skew_ns = skew_ms * 1_000_000
        return timestamp_ns + skew_ns
