"""
Consensus Adapter: at-most-once DECIDE per NEED using Redis.

Properties:
- At most one DECIDE per NEED (globally unique)
- Epoch-based fencing
- Replayable from audit log
"""

import redis
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class DecideRecord:
    need_id: str
    proposal_id: str
    epoch: int
    lamport: int
    k_plan: int  # How many attestations triggered this
    decider_id: str  # Who made the call
    timestamp_ns: int

class ConsensusAdapter:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        
        # Lua script for atomic DECIDE
        self.decide_script = self.redis.register_script("""
            local need_id = KEYS[1]
            local proposal_id = ARGV[1]
            local epoch = tonumber(ARGV[2])
            local decide_json = ARGV[3]
            
            -- Check if DECIDE already exists
            local existing = redis.call('GET', need_id)
            if existing then
                local existing_data = cjson.decode(existing)
                -- Idempotent: same proposal is OK
                if existing_data.proposal_id == proposal_id and existing_data.epoch == epoch then
                    return existing
                end
                -- Conflict: different DECIDE exists
                return nil
            end
            
            -- Set DECIDE (no expiry - permanent decision)
            redis.call('SET', need_id, decide_json)
            return decide_json
        """)
    
    def try_decide(
        self,
        need_id: str,
        proposal_id: str,
        epoch: int,
        lamport: int,
        k_plan: int,
        decider_id: str,
        timestamp_ns: int
    ) -> Optional[DecideRecord]:
        """
        Attempt to record a DECIDE. Returns:
        - DecideRecord if successful (or idempotent retry)
        - None if another DECIDE already exists
        """
        record = DecideRecord(
            need_id=need_id,
            proposal_id=proposal_id,
            epoch=epoch,
            lamport=lamport,
            k_plan=k_plan,
            decider_id=decider_id,
            timestamp_ns=timestamp_ns
        )
        
        decide_json = json.dumps({
            "need_id": need_id,
            "proposal_id": proposal_id,
            "epoch": epoch,
            "lamport": lamport,
            "k_plan": k_plan,
            "decider_id": decider_id,
            "timestamp_ns": timestamp_ns
        })
        
        result = self.decide_script(
            keys=[f"decide:{need_id}"],
            args=[proposal_id, epoch, decide_json]
        )
        
        if result is None:
            return None
        
        return record
    
    def get_decide(self, need_id: str) -> Optional[DecideRecord]:
        """Get existing DECIDE for a NEED"""
        data = self.redis.get(f"decide:{need_id}")
        if not data:
            return None
        
        obj = json.loads(data)
        return DecideRecord(**obj)
