"""
Migration Monitoring

Tracks message delivery across NATS and P2P transports to monitor
migration progress and detect divergence.
"""

import time
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TransportStats:
    """Statistics for a transport"""
    name: str
    messages_sent: int = 0
    messages_received: int = 0
    errors: int = 0
    last_success: float = 0.0
    last_error: float = 0.0
    
    def get_success_rate(self) -> float:
        """Calculate success rate"""
        total = self.messages_sent + self.errors
        if total == 0:
            return 0.0
        return self.messages_sent / total


@dataclass
class MigrationMetrics:
    """Overall migration metrics"""
    nats_stats: TransportStats = field(default_factory=lambda: TransportStats("NATS"))
    p2p_stats: TransportStats = field(default_factory=lambda: TransportStats("P2P"))
    duplicate_count: int = 0
    divergence_count: int = 0
    start_time: float = field(default_factory=time.time)
    
    def get_runtime(self) -> float:
        """Get runtime in seconds"""
        return time.time() - self.start_time
    
    def get_health_score(self) -> float:
        """
        Calculate overall health score (0.0 - 1.0).
        
        Considers success rates and divergence.
        """
        nats_success = self.nats_stats.get_success_rate()
        p2p_success = self.p2p_stats.get_success_rate()
        
        # Average success rate
        avg_success = (nats_success + p2p_success) / 2.0
        
        # Penalty for divergence
        total_messages = max(
            self.nats_stats.messages_sent + self.p2p_stats.messages_sent,
            1
        )
        divergence_rate = self.divergence_count / total_messages
        
        # Health = success - divergence penalty
        health = max(0.0, avg_success - divergence_rate)
        
        return health


class MigrationMonitor:
    """
    Monitors message delivery across transports.
    
    Tracks success rates, detects divergence, and logs migration progress.
    """
    
    def __init__(self):
        """Initialize migration monitor"""
        self.metrics = MigrationMetrics()
        
        # Message tracking: msg_id -> {nats: bool, p2p: bool}
        self.message_delivery: Dict[str, Dict[str, bool]] = {}
        
        # Divergence alerts
        self.divergence_threshold = 0.05  # 5%
        self.last_alert_time = 0.0
        self.alert_cooldown = 60.0  # seconds
        
        logger.info("Migration monitor initialized")
    
    def record_send(self, msg_id: str, transport: str):
        """
        Record message send.
        
        Args:
            msg_id: Message identifier
            transport: Transport name (NATS or P2P)
        """
        if transport.upper() == "NATS":
            self.metrics.nats_stats.messages_sent += 1
            self.metrics.nats_stats.last_success = time.time()
        elif transport.upper() == "P2P":
            self.metrics.p2p_stats.messages_sent += 1
            self.metrics.p2p_stats.last_success = time.time()
        
        logger.debug(f"Sent via {transport}: {msg_id}")
    
    def record_receive(self, msg_id: str, transport: str):
        """
        Record message receive.
        
        Args:
            msg_id: Message identifier
            transport: Transport name (NATS or P2P)
        """
        if transport.upper() == "NATS":
            self.metrics.nats_stats.messages_received += 1
        elif transport.upper() == "P2P":
            self.metrics.p2p_stats.messages_received += 1
        
        # Track delivery
        if msg_id not in self.message_delivery:
            self.message_delivery[msg_id] = {"nats": False, "p2p": False}
        
        transport_key = transport.lower()
        if self.message_delivery[msg_id].get(transport_key):
            # Duplicate
            self.metrics.duplicate_count += 1
            logger.debug(f"Duplicate message from {transport}: {msg_id}")
        else:
            self.message_delivery[msg_id][transport_key] = True
        
        logger.debug(f"Received via {transport}: {msg_id}")
    
    def record_error(self, transport: str, error: str):
        """
        Record transport error.
        
        Args:
            transport: Transport name
            error: Error description
        """
        if transport.upper() == "NATS":
            self.metrics.nats_stats.errors += 1
            self.metrics.nats_stats.last_error = time.time()
        elif transport.upper() == "P2P":
            self.metrics.p2p_stats.errors += 1
            self.metrics.p2p_stats.last_error = time.time()
        
        logger.warning(f"Error on {transport}: {error}")
    
    def check_divergence(self):
        """
        Check for divergence between transports.
        
        Divergence occurs when messages arrive via one transport but not the other.
        """
        divergent_messages = []
        
        for msg_id, delivery in self.message_delivery.items():
            nats_delivered = delivery.get("nats", False)
            p2p_delivered = delivery.get("p2p", False)
            
            # Only one transport delivered
            if nats_delivered != p2p_delivered:
                divergent_messages.append(msg_id)
        
        divergence_count = len(divergent_messages)
        
        if divergence_count > self.metrics.divergence_count:
            self.metrics.divergence_count = divergence_count
            
            # Check if we should alert
            self._check_divergence_alert(divergence_count)
        
        return divergent_messages
    
    def _check_divergence_alert(self, divergence_count: int):
        """Alert if divergence exceeds threshold"""
        total_messages = len(self.message_delivery)
        if total_messages == 0:
            return
        
        divergence_rate = divergence_count / total_messages
        
        # Only alert if rate exceeds threshold and cooldown expired
        if divergence_rate > self.divergence_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                logger.error(
                    f"DIVERGENCE ALERT: {divergence_rate:.1%} of messages "
                    f"({divergence_count}/{total_messages}) show transport divergence"
                )
                self.last_alert_time = current_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Get migration statistics"""
        divergent = self.check_divergence()
        
        return {
            "runtime_seconds": self.metrics.get_runtime(),
            "health_score": self.metrics.get_health_score(),
            "nats": {
                "sent": self.metrics.nats_stats.messages_sent,
                "received": self.metrics.nats_stats.messages_received,
                "errors": self.metrics.nats_stats.errors,
                "success_rate": self.metrics.nats_stats.get_success_rate()
            },
            "p2p": {
                "sent": self.metrics.p2p_stats.messages_sent,
                "received": self.metrics.p2p_stats.messages_received,
                "errors": self.metrics.p2p_stats.errors,
                "success_rate": self.metrics.p2p_stats.get_success_rate()
            },
            "duplicates": self.metrics.duplicate_count,
            "divergent_messages": len(divergent),
            "total_tracked": len(self.message_delivery)
        }
    
    def log_status(self):
        """Log current migration status"""
        stats = self.get_stats()
        
        logger.info("=== Migration Status ===")
        logger.info(f"Runtime: {stats['runtime_seconds']:.1f}s")
        logger.info(f"Health Score: {stats['health_score']:.2%}")
        logger.info(f"NATS: {stats['nats']['sent']} sent, "
                   f"{stats['nats']['received']} received, "
                   f"{stats['nats']['success_rate']:.1%} success")
        logger.info(f"P2P: {stats['p2p']['sent']} sent, "
                   f"{stats['p2p']['received']} received, "
                   f"{stats['p2p']['success_rate']:.1%} success")
        logger.info(f"Duplicates: {stats['duplicates']}")
        logger.info(f"Divergent: {stats['divergent_messages']}")
        logger.info("=" * 24)
