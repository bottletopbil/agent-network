"""
Plan Patching: Validate and merge patches with deterministic conflict resolution.

Conflict Resolution Rules:
- Concurrent ADD_TASK: Both kept (G-Set); if same task_id, higher lamport wins
- Concurrent STATE updates: Higher lamport wins (LWW)
- Concurrent LINK: Both kept if no cycle
- Conflicting patches: Deterministic merge by (lamport, actor_id)
"""

import uuid
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from plan_store import OpType, PlanOp, PlanStore


@dataclass
class PlanPatch:
    """
    A patch representing a set of operations to apply to the plan.
    """

    patch_id: str
    actor_id: str
    base_lamport: int  # Patch applies after this lamport
    ops: List[Dict[str, Any]] = field(default_factory=list)
    timestamp_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "patch_id": self.patch_id,
            "actor_id": self.actor_id,
            "base_lamport": self.base_lamport,
            "ops": self.ops,
            "timestamp_ns": self.timestamp_ns,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "PlanPatch":
        """Create PlanPatch from dictionary"""
        return PlanPatch(
            patch_id=data["patch_id"],
            actor_id=data["actor_id"],
            base_lamport=data["base_lamport"],
            ops=data.get("ops", []),
            timestamp_ns=data.get("timestamp_ns", 0),
        )


class PatchValidator:
    """
    Validates patches and handles conflict detection and merge.
    """

    def __init__(self, plan_store: Optional[PlanStore] = None):
        self.plan_store = plan_store

    def validate_patch(
        self, patch: PlanPatch, current_plan: Optional[PlanStore] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate patch structure and operations.

        Args:
            patch: The patch to validate
            current_plan: Optional plan store to validate against

        Returns:
            (is_valid, error_message)
        """
        # Validate patch structure
        if not patch.patch_id:
            return False, "Missing patch_id"

        if not patch.actor_id:
            return False, "Missing actor_id"

        if patch.base_lamport < 0:
            return False, "Invalid base_lamport (must be >= 0)"

        if not patch.ops:
            return False, "Empty ops list"

        # Validate each operation
        for idx, op_data in enumerate(patch.ops):
            op_type_str = op_data.get("op_type")
            task_id = op_data.get("task_id")

            if not op_type_str:
                return False, f"Op {idx}: Missing op_type"

            if not task_id:
                return False, f"Op {idx}: Missing task_id"

            # Validate op_type is valid
            try:
                OpType(op_type_str)
            except ValueError:
                return False, f"Op {idx}: Invalid op_type '{op_type_str}'"

            # Validate op-specific fields
            if op_type_str == "STATE":
                if "state" not in op_data.get("payload", {}):
                    return False, f"Op {idx}: STATE op missing 'state' in payload"

            elif op_type_str == "LINK":
                payload = op_data.get("payload", {})
                if "parent" not in payload or "child" not in payload:
                    return (
                        False,
                        f"Op {idx}: LINK op missing 'parent' or 'child' in payload",
                    )

        return True, None

    def detect_conflicts(self, patch: PlanPatch, other_patches: List[PlanPatch]) -> List[str]:
        """
        Detect conflicts between this patch and other patches.

        Args:
            patch: The patch to check
            other_patches: Other patches to check against

        Returns:
            List of conflict descriptions (empty if no conflicts)
        """
        conflicts = []

        # Build operation sets for comparison
        patch_ops = {(op["task_id"], op["op_type"]): op for op in patch.ops}

        for other in other_patches:
            if other.patch_id == patch.patch_id:
                continue  # Don't compare with self

            for other_op in other.ops:
                key = (other_op["task_id"], other_op["op_type"])

                # Check for conflicting operations
                if key in patch_ops:
                    our_op = patch_ops[key]

                    # STATE conflicts: Higher lamport wins (LWW)
                    if other_op["op_type"] == "STATE":
                        if our_op.get("payload", {}).get("state") != other_op.get(
                            "payload", {}
                        ).get("state"):
                            conflicts.append(
                                f"STATE conflict on task {other_op['task_id']}: "
                                f"patch {patch.patch_id} vs {other.patch_id}"
                            )

                    # ADD_TASK conflicts: Both kept, but note the conflict
                    elif other_op["op_type"] == "ADD_TASK":
                        if our_op.get("payload") != other_op.get("payload"):
                            conflicts.append(
                                f"ADD_TASK conflict on task {other_op['task_id']}: "
                                f"different payloads in {patch.patch_id} vs {other.patch_id}"
                            )

        return conflicts

    def _detect_cycle(self, edges: List[Tuple[str, str]], new_edge: Tuple[str, str]) -> bool:
        """
        Detect if adding new_edge would create a cycle.

        Args:
            edges: Existing edges as (parent, child) tuples
            new_edge: New edge to test

        Returns:
            True if cycle would be created
        """
        # Build adjacency list
        graph: Dict[str, Set[str]] = {}
        all_edges = edges + [new_edge]

        for parent, child in all_edges:
            if parent not in graph:
                graph[parent] = set()
            graph[parent].add(child)

        # DFS to detect cycle
        def has_cycle_from(node: str, visited: Set[str], rec_stack: Set[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle_from(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        # Check all nodes
        visited: Set[str] = set()
        for node in graph.keys():
            if node not in visited:
                if has_cycle_from(node, visited, set()):
                    return True

        return False

    def merge_patches(self, patches: List[PlanPatch]) -> List[PlanOp]:
        """
        Merge multiple patches using deterministic conflict resolution.

        Rules:
        - Sort patches by (base_lamport, actor_id)
        - Apply in sorted order
        - For STATE conflicts: Higher lamport wins
        - For ADD_TASK conflicts with same task_id: Higher lamport wins
        - For LINK: Check for cycles, reject if cycle detected

        Args:
            patches: List of patches to merge

        Returns:
            List of merged PlanOp objects
        """
        if not patches:
            return []

        # Sort patches deterministically by (base_lamport, actor_id)
        sorted_patches = sorted(patches, key=lambda p: (p.base_lamport, p.actor_id))

        # Track operations by (task_id, op_type) for conflict resolution
        merged_ops: Dict[Tuple[str, str], Dict[str, Any]] = {}
        add_task_ops: Dict[str, Dict[str, Any]] = {}  # Track ADD_TASK by task_id
        link_edges: List[Tuple[str, str]] = []
        result_ops: List[PlanOp] = []

        current_lamport = max(p.base_lamport for p in sorted_patches) + 1

        for patch in sorted_patches:
            for op_data in patch.ops:
                op_type = op_data["op_type"]
                task_id = op_data["task_id"]
                key = (task_id, op_type)

                if op_type == "ADD_TASK":
                    # G-Set: Both kept, but if same task_id, higher lamport wins
                    if task_id in add_task_ops:
                        # Compare lamports (patch base_lamport is proxy)
                        if patch.base_lamport > add_task_ops[task_id]["_patch_lamport"]:
                            add_task_ops[task_id] = {
                                **op_data,
                                "_patch_lamport": patch.base_lamport,
                                "_actor": patch.actor_id,
                            }
                    else:
                        add_task_ops[task_id] = {
                            **op_data,
                            "_patch_lamport": patch.base_lamport,
                            "_actor": patch.actor_id,
                        }

                elif op_type == "STATE":
                    # LWW: Higher lamport wins
                    if key in merged_ops:
                        if patch.base_lamport > merged_ops[key]["_patch_lamport"]:
                            merged_ops[key] = {
                                **op_data,
                                "_patch_lamport": patch.base_lamport,
                                "_actor": patch.actor_id,
                            }
                    else:
                        merged_ops[key] = {
                            **op_data,
                            "_patch_lamport": patch.base_lamport,
                            "_actor": patch.actor_id,
                        }

                elif op_type == "LINK":
                    # Check for cycles
                    parent = op_data["payload"]["parent"]
                    child = op_data["payload"]["child"]
                    new_edge = (parent, child)

                    if not self._detect_cycle(link_edges, new_edge):
                        link_edges.append(new_edge)
                        merged_ops[key] = {
                            **op_data,
                            "_patch_lamport": patch.base_lamport,
                            "_actor": patch.actor_id,
                        }
                    # else: silently drop the LINK that would create a cycle

                else:
                    # Other ops: keep all (G-Set semantics)
                    merged_ops[key] = {
                        **op_data,
                        "_patch_lamport": patch.base_lamport,
                        "_actor": patch.actor_id,
                    }

        # Convert to PlanOp objects
        # First, add ADD_TASK ops
        for task_id, op_data in add_task_ops.items():
            op = PlanOp(
                op_id=str(uuid.uuid4()),
                thread_id="merged",  # Will be set by caller
                lamport=current_lamport,
                actor_id=op_data["_actor"],
                op_type=OpType(op_data["op_type"]),
                task_id=task_id,
                payload=op_data.get("payload", {}),
                timestamp_ns=0,
            )
            result_ops.append(op)
            current_lamport += 1

        # Then add other ops
        for (task_id, op_type_str), op_data in merged_ops.items():
            if op_type_str == "ADD_TASK":
                continue  # Already added

            op = PlanOp(
                op_id=str(uuid.uuid4()),
                thread_id="merged",
                lamport=current_lamport,
                actor_id=op_data["_actor"],
                op_type=OpType(op_type_str),
                task_id=task_id,
                payload=op_data.get("payload", {}),
                timestamp_ns=0,
            )
            result_ops.append(op)
            current_lamport += 1

        return result_ops
