"""
Merge handler for partition recovery.

Provides deterministic conflict resolution when network partitions heal
and multiple conflicting DECIDE records exist for the same NEED.
"""
from typing import List, Dict, Any
from dataclasses import dataclass
import time


@dataclass
class DecideConflict:
    """
    Represents a conflict between two DECIDE records.
    
    Occurs when network partition results in different DECIDEs
    for the same NEED in different partitions.
    """
    need_id: str
    local_decide: Dict[str, Any]
    remote_decide: Dict[str, Any]
    winner: str  # 'local' or 'remote'
    reason: str  # Why this winner was chosen


class MergeHandler:
    """
    Handles merging of DECIDE records after partition heal.
    
    Uses deterministic rules to resolve conflicts:
    1. Highest epoch wins
    2. If epochs equal, highest lamport wins
    3. If lamport equal, lexicographically first decider_id wins
    """
    
    def highest_epoch_wins(
        self,
        local_decide: Dict[str, Any],
        remote_decide: Dict[str, Any]
    ) -> str:
        """
        Deterministic merge rule: highest epoch wins.
        
        If epochs equal, use lamport as tiebreaker.
        If lamport equal, use decider_id (lexicographic).
        
        Args:
            local_decide: DECIDE record from local partition
            remote_decide: DECIDE record from remote partition
            
        Returns:
            'local' if local wins, 'remote' if remote wins
        """
        local_epoch = local_decide.get('epoch', 0)
        remote_epoch = remote_decide.get('epoch', 0)
        
        # Rule 1: Highest epoch wins
        if local_epoch != remote_epoch:
            return 'local' if local_epoch > remote_epoch else 'remote'
        
        # Rule 2: Same epoch, compare lamport
        local_lamport = local_decide.get('lamport', 0)
        remote_lamport = remote_decide.get('lamport', 0)
        
        if local_lamport != remote_lamport:
            return 'local' if local_lamport > remote_lamport else 'remote'
        
        # Rule 3: Same lamport, compare decider_id (lexicographic)
        local_id = local_decide.get('decider_id', '')
        remote_id = remote_decide.get('decider_id', '')
        
        # Lower lexicographic value wins (deterministic tie-breaker)
        return 'local' if local_id < remote_id else 'remote'
    
    def merge_on_heal(
        self,
        local_decides: List[Dict[str, Any]],
        remote_decides: List[Dict[str, Any]]
    ) -> List[DecideConflict]:
        """
        Merge DECIDE records after partition heal.
        
        Finds conflicting DECIDEs (same need_id, different proposal_id)
        and resolves using highest_epoch_wins.
        
        Args:
            local_decides: DECIDE records from local partition
            remote_decides: DECIDE records from remote partition
            
        Returns:
            List of conflicts with resolution
        """
        conflicts = []
        
        # Index by need_id for efficient lookup
        local_by_need = {d['need_id']: d for d in local_decides}
        remote_by_need = {d['need_id']: d for d in remote_decides}
        
        # Find conflicting DECIDEs (same need, different proposals)
        for need_id in set(local_by_need.keys()) & set(remote_by_need.keys()):
            local_d = local_by_need[need_id]
            remote_d = remote_by_need[need_id]
            
            # Check if same proposal (no conflict)
            if local_d.get('proposal_id') == remote_d.get('proposal_id'):
                continue  # Same decision, no conflict
            
            # Different proposals - conflict!
            winner = self.highest_epoch_wins(local_d, remote_d)
            
            conflicts.append(DecideConflict(
                need_id=need_id,
                local_decide=local_d,
                remote_decide=remote_d,
                winner=winner,
                reason=f"Epoch {local_d.get('epoch', 0)} vs {remote_d.get('epoch', 0)}"
            ))
        
        return conflicts
    
    def mark_orphaned(
        self,
        decide: Dict[str, Any],
        winning_epoch: int,
        plan_store
    ) -> None:
        """
        Mark losing DECIDE branch as orphaned.
        
        Annotates the task in plan_store to indicate it was
        orphaned by a higher-epoch decision.
        
        Args:
            decide: The DECIDE record that lost
            winning_epoch: Epoch of the winning DECIDE
            plan_store: PlanStore instance to annotate
        """
        task_id = decide.get('task_id') or decide.get('need_id')
        if not task_id:
            return
        
        # Annotate task as orphaned
        try:
            plan_store.annotate_task(task_id, {
                'orphaned': True,
                'orphaned_by_epoch': winning_epoch,
                'orphaned_proposal': decide.get('proposal_id'),
                'orphaned_at_ns': time.time_ns(),
                'orphan_reason': f"Lost to epoch {winning_epoch}"
            })
            print(f"[MERGE] Marked task {task_id} as orphaned by epoch {winning_epoch}")
        except Exception as e:
            print(f"[MERGE] WARNING: Failed to mark orphaned: {e}")
