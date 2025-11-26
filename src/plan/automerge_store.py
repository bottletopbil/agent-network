"""
Automerge-style CRDT Plan Store

Pure Python implementation of CRDT semantics for distributed plan storage:
- G-Set (Grow-only Set) for ops and edges
- LWW (Last-Write-Wins) for annotations
- Monotonic state updates (higher Lamport clock wins)
- Merge support for multi-peer synchronization

This provides Automerge-like functionality without requiring Rust compilation.
"""

import json
import copy
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from plan_store import OpType, TaskState, PlanOp
from plan.views import TaskView, GraphView


@dataclass
class CRDTDocument:
    """CRDT document with Automerge-like semantics"""
    tasks: Dict[str, Dict[str, Any]]  # task_id -> task data
    edges: Dict[str, List[str]]  # parent_id -> [child_ids]
    annotations: Dict[str, Dict[str, Any]]  # task_id -> {key: {value, lamport}}
    ops: List[Dict[str, Any]]  # All operations for replay
    version: int = 0  # Document version for tracking changes


class AutomergePlanStore:
    """
    CRDT-based plan store with Automerge semantics.
    
    Provides:
    - G-Set semantics for ops (append-only)
    - G-Set semantics for edges (grow-only)
    - Monotonic state updates (higher lamport wins)
    - LWW semantics for annotations
    - Save/load/merge functionality
    - Tiered storage with automatic pruning
    """
    
    def __init__(self, enable_tiered_storage: bool = False):
        """
        Initialize empty Automerge document.
        
        Args:
            enable_tiered_storage: Enable automatic tiering and pruning
        """
        self.enable_tiered_storage = enable_tiered_storage
        self.tiered_storage = None
        self.current_epoch = 0
        
        if enable_tiered_storage:
            from checkpoint.pruning import TieredStorage
            self.tiered_storage = TieredStorage()
        
        self._init_schema()
    
    def _init_schema(self):
        """Create document with CRDT-compatible structure"""
        self.doc = CRDTDocument(
            tasks={},
            edges={},
            annotations={},
            ops=[],
            version=0
        )
        self._op_ids: Set[str] = set()  # Track op IDs for deduplication
        
        # Initialize views
        self.task_view: Optional[TaskView] = None
        self.graph_view: Optional[GraphView] = None
        self._update_views()
    
    def _update_views(self):
        """Update materialized views after state changes"""
        self.task_view = TaskView(self.doc.tasks)
        self.graph_view = GraphView(self.doc.edges)
    
    def append_op(self, op: PlanOp) -> None:
        """
        Append operation to log and apply to state.
        
        Uses G-Set semantics - operations are idempotent and can be added
        multiple times without effect if op_id already exists.
        
        Args:
            op: PlanOp to append
        """
        # Deduplicate based on op_id (G-Set property)
        if op.op_id in self._op_ids:
            return  # Already applied
        
        # Add to op log
        op_dict = {
            "op_id": op.op_id,
            "thread_id": op.thread_id,
            "lamport": op.lamport,
            "actor_id": op.actor_id,
            "op_type": op.op_type.value,
            "task_id": op.task_id,
            "payload": op.payload,
            "timestamp_ns": op.timestamp_ns
        }
        self.doc.ops.append(op_dict)
        self._op_ids.add(op.op_id)
        self.doc.version += 1
        
        # Apply to derived state
        self._apply_to_state(self.doc, op)
        
        # Update views
        self._update_views()
    
    def _apply_to_state(self, doc: CRDTDocument, op: PlanOp) -> None:
        """
        Apply operation to document state using CRDT semantics.
        
        Args:
            doc: CRDT document to update
            op: Operation to apply
        """
        if op.op_type == OpType.ADD_TASK:
            # G-Set: Add task if not exists (idempotent)
            if op.task_id not in doc.tasks:
                doc.tasks[op.task_id] = {
                    "task_id": op.task_id,
                    "thread_id": op.thread_id,
                    "task_type": op.payload.get("type"),
                    "state": TaskState.DRAFT.value,
                    "last_lamport": op.lamport
                }
        
        elif op.op_type == OpType.STATE:
            # Monotonic: Only update if lamport is higher
            if op.task_id not in doc.tasks:
                # Create task if it doesn't exist
                doc.tasks[op.task_id] = {
                    "task_id": op.task_id,
                    "thread_id": op.thread_id,
                    "task_type": None,
                    "state": op.payload["state"],
                    "last_lamport": op.lamport
                }
            else:
                # Update only if newer
                task = doc.tasks[op.task_id]
                if op.lamport > task["last_lamport"]:
                    task["state"] = op.payload["state"]
                    task["last_lamport"] = op.lamport
        
        elif op.op_type == OpType.LINK:
            # G-Set: Add edge if not exists (idempotent)
            parent = op.payload["parent"]
            child = op.payload["child"]
            
            if parent not in doc.edges:
                doc.edges[parent] = []
            
            if child not in doc.edges[parent]:
                doc.edges[parent].append(child)
        
        elif op.op_type == OpType.ANNOTATE:
            # LWW (Last-Write-Wins): Update if lamport is higher
            if op.task_id not in doc.annotations:
                doc.annotations[op.task_id] = {}
            
            task_annotations = doc.annotations[op.task_id]
            
            for key, value in op.payload.items():
                if key not in task_annotations:
                    # First write
                    task_annotations[key] = {
                        "value": value,
                        "lamport": op.lamport
                    }
                else:
                    # LWW: Update if newer
                    if op.lamport > task_annotations[key]["lamport"]:
                        task_annotations[key] = {
                            "value": value,
                            "lamport": op.lamport
                        }
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """
        Get current task state.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task dictionary or None if not found
        """
        task = self.doc.tasks.get(task_id)
        if not task:
            return None
        
        # Include annotations if they exist
        result = copy.deepcopy(task)
        if task_id in self.doc.annotations:
            result["annotations"] = {
                key: ann["value"]
                for key, ann in self.doc.annotations[task_id].items()
            }
        
        return result
    
    def get_ops_for_thread(self, thread_id: str) -> List[PlanOp]:
        """
        Get all operations for a thread.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            List of PlanOp objects, ordered by lamport
        """
        ops = []
        for op_dict in self.doc.ops:
            if op_dict["thread_id"] == thread_id:
                ops.append(PlanOp(
                    op_id=op_dict["op_id"],
                    thread_id=op_dict["thread_id"],
                    lamport=op_dict["lamport"],
                    actor_id=op_dict["actor_id"],
                    op_type=OpType(op_dict["op_type"]),
                    task_id=op_dict["task_id"],
                    payload=op_dict["payload"],
                    timestamp_ns=op_dict["timestamp_ns"]
                ))
        
        # Sort by lamport for deterministic order
        ops.sort(key=lambda op: op.lamport)
        return ops
    
    def get_save_data(self) -> bytes:
        """
        Serialize document to bytes for persistence.
        
        Returns:
            JSON-encoded document as bytes
        """
        doc_dict = {
            "tasks": self.doc.tasks,
            "edges": self.doc.edges,
            "annotations": self.doc.annotations,
            "ops": self.doc.ops,
            "version": self.doc.version
        }
        return json.dumps(doc_dict, indent=2).encode('utf-8')
    
    def load_from_data(self, data: bytes) -> None:
        """
        Load document from serialized bytes.
        
        Args:
            data: JSON-encoded document bytes
        """
        doc_dict = json.loads(data.decode('utf-8'))
        
        self.doc = CRDTDocument(
            tasks=doc_dict["tasks"],
            edges=doc_dict["edges"],
            annotations=doc_dict["annotations"],
            ops=doc_dict["ops"],
            version=doc_dict.get("version", 0)
        )
        
        # Rebuild op_ids set for deduplication
        self._op_ids = {op["op_id"] for op in self.doc.ops}
    
    def merge_with_peer(self, peer_data: bytes) -> None:
        """
        Merge with a peer's document using CRDT merge semantics.
        
        Steps:
        1. Load peer document
        2. Merge ops (G-Set union with deduplication)
        3. Replay all ops to rebuild state deterministically
        
        Args:
            peer_data: Serialized peer document
        """
        peer_dict = json.loads(peer_data.decode('utf-8'))
        
        # Collect all ops from both documents
        our_op_ids = self._op_ids
        peer_op_ids = {op["op_id"] for op in peer_dict["ops"]}
        
        # Find new ops from peer (G-Set union)
        new_ops = [
            op for op in peer_dict["ops"]
            if op["op_id"] not in our_op_ids
        ]
        
        # Add peer's new ops to our log
        self.doc.ops.extend(new_ops)
        for op in new_ops:
            self._op_ids.add(op["op_id"])
        
        # Sort all ops by lamport for deterministic replay
        self.doc.ops.sort(key=lambda op: op["lamport"])
        
        # Rebuild state from scratch by replaying all ops
        self._rebuild_state_from_ops()
        
        # Update views
        self._update_views()
        
        self.doc.version += 1
    
    def _rebuild_state_from_ops(self) -> None:
        """
        Rebuild derived state by replaying all ops in lamport order.
        
        This ensures deterministic state regardless of merge order.
        """
        # Clear derived state
        self.doc.tasks = {}
        self.doc.edges = {}
        self.doc.annotations = {}
        
        # Replay all ops
        for op_dict in self.doc.ops:
            op = PlanOp(
                op_id=op_dict["op_id"],
                thread_id=op_dict["thread_id"],
                lamport=op_dict["lamport"],
                actor_id=op_dict["actor_id"],
                op_type=OpType(op_dict["op_type"]),
                task_id=op_dict["task_id"],
                payload=op_dict["payload"],
                timestamp_ns=op_dict["timestamp_ns"]
            )
            self._apply_to_state(self.doc, op)
    
    def get_edges(self, parent_id: str) -> List[str]:
        """
        Get children of a parent task.
        
        Args:
            parent_id: Parent task ID
            
        Returns:
            List of child task IDs
        """
        return self.doc.edges.get(parent_id, [])
    
    def get_all_tasks(self) -> List[Dict]:
        """
        Get all tasks in the document.
        
        Returns:
            List of task dictionaries
        """
        tasks = []
        for task_id in self.doc.tasks:
            task = self.get_task(task_id)
            if task:
                tasks.append(task)
        return tasks
    
    def checkpoint_and_prune(self, epoch: int) -> Optional[dict]:
        """
        Create checkpoint and prune old operations.
        
        Args:
            epoch: Current epoch number
            
        Returns:
            Pruning stats if tiered storage enabled, None otherwise
        """
        if not self.enable_tiered_storage or not self.tiered_storage:
            return None
        
        from checkpoint.pruning import PruningManager, PruningPolicy
        
        # Update current epoch
        self.current_epoch = epoch
        
        # Create pruning manager
        manager = PruningManager(
            policy=PruningPolicy(keep_epochs=10),
            storage=self.tiered_storage
        )
        
        # Add epoch to ops for pruning
        ops_with_epoch = []
        for op_dict in self.doc.ops:
            op_with_epoch = op_dict.copy()
            # Estimate epoch from timestamp or use current
            op_with_epoch["epoch"] = epoch - 1  # Assume recent
            ops_with_epoch.append(op_with_epoch)
        
        # Prune old ops
        moved, kept = manager.prune_before_epoch(ops_with_epoch, epoch)
        
        return manager.get_stats()

