"""
Raft Consensus Adapter using etcd for atomic DECIDE operations.

Provides distributed consensus for DECIDE records with:
- 256-bucket sharding via SHA256 hashing
- Atomic compare-and-set via etcd transactions
- Idempotent retry support
- At-most-once DECIDE guarantee
"""

import etcd3
import json
import hashlib
from typing import Optional, List, Tuple
from dataclasses import dataclass, asdict
from consensus.epochs import epoch_manager


@dataclass
class DecideRecord:
    """Record of a DECIDE consensus decision"""

    need_id: str
    proposal_id: str
    epoch: int
    lamport: int
    k_plan: int
    decider_id: str
    timestamp_ns: int


class RaftConsensusAdapter:
    """
    Raft-based consensus adapter using etcd.

    Uses 256 buckets for sharding based on hash(need_id).
    Each DECIDE is stored with atomic compare-and-set semantics.
    """

    def __init__(self, etcd_hosts: Optional[List[Tuple[str, int]]] = None):
        """
        Initialize Raft consensus adapter.

        Args:
            etcd_hosts: List of (host, port) tuples. Default: [('localhost', 2379)]
        """
        if etcd_hosts is None:
            etcd_hosts = [("localhost", 2379)]

        host, port = etcd_hosts[0]
        self.client = etcd3.client(host=host, port=port)
        self.num_buckets = 256

    def get_bucket_for_need(self, need_id: str) -> int:
        """
        Hash need_id to bucket number 0-255.

        Uses SHA256 for consistent hashing.

        Args:
            need_id: NEED identifier

        Returns:
            Bucket number 0-255
        """
        hash_bytes = hashlib.sha256(need_id.encode()).digest()
        return hash_bytes[0]  # First byte gives 0-255

    def get_decide_key(self, need_id: str) -> str:
        """
        Build sharded etcd key for DECIDE record.

        Args:
            need_id: NEED identifier

        Returns:
            Bucketed key path for DECIDE storage
        """
        bucket = self.get_bucket_for_need(need_id)
        return f"/decide/bucket-{bucket:03d}/{need_id}"

    def try_decide(
        self,
        need_id: str,
        proposal_id: str,
        epoch: int,
        lamport: int,
        k_plan: int,
        decider_id: str,
        timestamp_ns: int,
    ) -> Optional[DecideRecord]:
        """
        Attempt atomic DECIDE using etcd transaction.

        Uses compare-and-set to ensure at-most-once DECIDE per NEED.
        Supports idempotent retries (same proposal returns success).

        Args:
            need_id: NEED being decided
            proposal_id: Winning proposal
            epoch: Current epoch number
            lamport: Lamport timestamp
            k_plan: Quorum size that triggered DECIDE
            decider_id: ID of entity making DECIDE
            timestamp_ns: Timestamp in nanoseconds

        Returns:
            DecideRecord if successful or idempotent retry, None if conflict
        """
        current_epoch = epoch_manager.get_current_epoch()
        if epoch < current_epoch:
            return None

        key = self.get_decide_key(need_id)

        record = DecideRecord(
            need_id=need_id,
            proposal_id=proposal_id,
            epoch=epoch,
            lamport=lamport,
            k_plan=k_plan,
            decider_id=decider_id,
            timestamp_ns=timestamp_ns,
        )

        record_json = json.dumps(asdict(record))

        # Atomic compare-and-set: only set if key doesn't exist
        # compare: key create revision == 0 (doesn't exist)
        # success: put the key
        # failure: do nothing
        success = self.client.transaction(
            compare=[self.client.transactions.create(key) == 0],
            success=[self.client.transactions.put(key, record_json)],
            failure=[],
        )[0]

        if success:
            return record

        # Check if existing DECIDE matches (idempotent retry)
        existing_value, _ = self.client.get(key)
        if existing_value:
            existing_data = json.loads(existing_value.decode())
            if existing_data["proposal_id"] == proposal_id and existing_data["epoch"] == epoch:
                return record  # Idempotent retry succeeded

        return None  # Conflict: different DECIDE exists

    def get_decide(self, need_id: str) -> Optional[DecideRecord]:
        """
        Get existing DECIDE for a NEED.

        Args:
            need_id: NEED identifier

        Returns:
            DecideRecord if exists, None otherwise
        """
        key = self.get_decide_key(need_id)
        value, _ = self.client.get(key)

        if not value:
            return None

        data = json.loads(value.decode())
        return DecideRecord(**data)

    def close(self):
        """Close etcd client connection"""
        self.client.close()
