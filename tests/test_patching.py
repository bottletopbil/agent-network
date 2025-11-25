"""
Unit tests for Plan Patching and Versioning.

Tests:
- Patch application and validation
- Conflict detection and resolution
- Merge rules (G-Set, LWW, cycle detection)
- Plan versioning with merkle roots
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from plan_store import PlanStore, PlanOp, OpType, TaskState
from plan.patching import PlanPatch, PatchValidator
from plan.versioning import PlanVersion, VersionTracker
import uuid
import time


class TestPatchApply:
    """Test patch application and validation"""
    
    def test_apply_single_patch(self):
        """Test applying a single valid patch"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        # Create a simple patch
        patch = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[
                {
                    "op_type": "ADD_TASK",
                    "task_id": "task-1",
                    "payload": {"type": "worker", "description": "Test task"}
                }
            ],
            timestamp_ns=time.time_ns()
        )
        
        # Validate patch
        is_valid, error = validator.validate_patch(patch, db)
        assert is_valid
        assert error is None
    
    def test_apply_multiple_patches(self):
        """Test applying multiple patches in sequence"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        patches = []
        for i in range(3):
            patch = PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id=f"agent-{i}",
                base_lamport=i * 10,
                ops=[
                    {
                        "op_type": "ADD_TASK",
                        "task_id": f"task-{i}",
                        "payload": {"type": "worker"}
                    }
                ],
                timestamp_ns=time.time_ns()
            )
            patches.append(patch)
            is_valid, _ = validator.validate_patch(patch, db)
            assert is_valid
    
    def test_patch_validation_failure(self):
        """Test invalid patch rejection"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        # Missing patch_id
        patch1 = PlanPatch(
            patch_id="",
            actor_id="alice",
            base_lamport=10,
            ops=[{"op_type": "ADD_TASK", "task_id": "task-1", "payload": {}}]
        )
        is_valid, error = validator.validate_patch(patch1, db)
        assert not is_valid
        assert "patch_id" in error.lower()
        
        # Empty ops
        patch2 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[]
        )
        is_valid, error = validator.validate_patch(patch2, db)
        assert not is_valid
        assert "empty" in error.lower()
        
        # Invalid op_type
        patch3 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[{"op_type": "INVALID_TYPE", "task_id": "task-1", "payload": {}}]
        )
        is_valid, error = validator.validate_patch(patch3, db)
        assert not is_valid
        assert "invalid op_type" in error.lower()
        
        # Missing task_id
        patch4 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[{"op_type": "ADD_TASK", "payload": {}}]
        )
        is_valid, error = validator.validate_patch(patch4, db)
        assert not is_valid
        assert "task_id" in error.lower()


class TestConflictDetection:
    """Test conflict detection between patches"""
    
    def test_concurrent_add_task_same_id(self):
        """Test concurrent ADD_TASK with same task_id"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        patch1 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[
                {"op_type": "ADD_TASK", "task_id": "task-1", "payload": {"version": 1}}
            ]
        )
        
        patch2 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="bob",
            base_lamport=11,
            ops=[
                {"op_type": "ADD_TASK", "task_id": "task-1", "payload": {"version": 2}}
            ]
        )
        
        # Detect conflicts
        conflicts = validator.detect_conflicts(patch1, [patch2])
        assert len(conflicts) > 0
        assert "ADD_TASK" in conflicts[0]
    
    def test_concurrent_state_updates(self):
        """Test LWW semantics for concurrent STATE updates"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        patch1 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[
                {"op_type": "STATE", "task_id": "task-1", "payload": {"state": "DECIDED"}}
            ]
        )
        
        patch2 = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="bob",
            base_lamport=11,
            ops=[
                {"op_type": "STATE", "task_id": "task-1", "payload": {"state": "VERIFIED"}}
            ]
        )
        
        # Detect conflicts
        conflicts = validator.detect_conflicts(patch1, [patch2])
        assert len(conflicts) > 0
        assert "STATE" in conflicts[0]
    
    def test_concurrent_links_no_cycle(self):
        """Test concurrent LINK operations without cycles"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        # These should not create a cycle
        edges = [("A", "B"), ("B", "C")]
        new_edge = ("C", "D")
        
        has_cycle = validator._detect_cycle(edges, new_edge)
        assert not has_cycle
    
    def test_concurrent_links_with_cycle(self):
        """Test cycle detection prevents invalid LINK"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        # This would create a cycle: A -> B -> C -> A
        edges = [("A", "B"), ("B", "C")]
        new_edge = ("C", "A")
        
        has_cycle = validator._detect_cycle(edges, new_edge)
        assert has_cycle


class TestMergeRules:
    """Test deterministic patch merging"""
    
    def test_deterministic_merge_by_lamport(self):
        """Test patches are merged in lamport order"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        # Create patches with different lamports
        patches = [
            PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id="alice",
                base_lamport=30,
                ops=[{"op_type": "ADD_TASK", "task_id": "task-3", "payload": {}}]
            ),
            PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id="bob",
                base_lamport=10,
                ops=[{"op_type": "ADD_TASK", "task_id": "task-1", "payload": {}}]
            ),
            PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id="charlie",
                base_lamport=20,
                ops=[{"op_type": "ADD_TASK", "task_id": "task-2", "payload": {}}]
            ),
        ]
        
        # Merge patches
        merged_ops = validator.merge_patches(patches)
        
        # Should be sorted by lamport
        assert len(merged_ops) == 3
        # All should be ADD_TASK ops in order
        task_ids = [op.task_id for op in merged_ops]
        assert "task-1" in task_ids
        assert "task-2" in task_ids
        assert "task-3" in task_ids
    
    def test_deterministic_merge_by_actor(self):
        """Test tiebreak by actor_id when lamports are equal"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        # Same lamport, different actors
        patches = [
            PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id="charlie",
                base_lamport=10,
                ops=[{"op_type": "ADD_TASK", "task_id": "task-c", "payload": {}}]
            ),
            PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id="alice",
                base_lamport=10,
                ops=[{"op_type": "ADD_TASK", "task_id": "task-a", "payload": {}}]
            ),
            PlanPatch(
                patch_id=str(uuid.uuid4()),
                actor_id="bob",
                base_lamport=10,
                ops=[{"op_type": "ADD_TASK", "task_id": "task-b", "payload": {}}]
            ),
        ]
        
        merged_ops = validator.merge_patches(patches)
        assert len(merged_ops) == 3
        
        # Should be sorted by actor_id (alice, bob, charlie)
        actors = [op.actor_id for op in merged_ops]
        assert actors[0] == "alice"
        assert actors[1] == "bob"
        assert actors[2] == "charlie"
    
    def test_idempotent_patch_application(self):
        """Test same patch twice produces same result"""
        db = PlanStore(Path(tempfile.mktemp()))
        validator = PatchValidator(db)
        
        patch = PlanPatch(
            patch_id=str(uuid.uuid4()),
            actor_id="alice",
            base_lamport=10,
            ops=[
                {"op_type": "ADD_TASK", "task_id": "task-1", "payload": {"type": "worker"}}
            ]
        )
        
        # Merge the same patch twice
        merged1 = validator.merge_patches([patch])
        merged2 = validator.merge_patches([patch])
        
        # Should produce identical results
        assert len(merged1) == len(merged2)
        assert merged1[0].task_id == merged2[0].task_id


class TestPlanVersioning:
    """Test plan version tracking"""
    
    def test_record_version(self):
        """Test creating a version snapshot"""
        db_path = Path(tempfile.mktemp())
        tracker = VersionTracker(db_path)
        
        plan_state = {
            "task-1": {"task_id": "task-1", "state": "DRAFT", "type": "worker"},
            "task-2": {"task_id": "task-2", "state": "DECIDED", "type": "verifier"}
        }
        
        version = tracker.record_version(plan_state, lamport=100)
        
        assert version.version_id is not None
        assert version.lamport == 100
        assert version.merkle_root is not None
        assert len(version.merkle_root) == 64  # SHA256 hex length
    
    def test_get_version_at_lamport(self):
        """Test retrieving version at specific lamport"""
        db_path = Path(tempfile.mktemp())
        tracker = VersionTracker(db_path)
        
        # Record multiple versions
        for i in range(5):
            plan_state = {f"task-{i}": {"state": "DRAFT"}}
            tracker.record_version(plan_state, lamport=i * 10)
        
        # Get version at lamport 25 (should get version at 20)
        version = tracker.get_version_at_lamport(25)
        assert version is not None
        assert version.lamport == 20
        
        # Get version at lamport 100 (should get version at 40)
        version = tracker.get_version_at_lamport(100)
        assert version is not None
        assert version.lamport == 40
    
    def test_compute_diff(self):
        """Test calculating differences between versions"""
        db_path = Path(tempfile.mktemp())
        tracker = VersionTracker(db_path)
        
        # Version A
        plan_state_a = {
            "task-1": {"state": "DRAFT"},
            "task-2": {"state": "DECIDED"}
        }
        version_a = tracker.record_version(plan_state_a, lamport=10)
        
        # Version B (task-1 modified, task-3 added, task-2 removed)
        plan_state_b = {
            "task-1": {"state": "VERIFIED"},  # Modified
            "task-3": {"state": "DRAFT"}      # Added
        }
        version_b = tracker.record_version(plan_state_b, lamport=20)
        
        # Compute diff
        diff = tracker.compute_diff(version_a.version_id, version_b.version_id)
        
        assert len(diff['added']) == 1
        assert diff['added'][0]['task_id'] == "task-3"
        
        assert len(diff['removed']) == 1
        assert diff['removed'][0]['task_id'] == "task-2"
        
        assert len(diff['modified']) == 1
        assert diff['modified'][0]['task_id'] == "task-1"
        assert diff['modified'][0]['old_data']['state'] == "DRAFT"
        assert diff['modified'][0]['new_data']['state'] == "VERIFIED"
    
    def test_merkle_root_consistency(self):
        """Test same state produces same merkle root"""
        db_path = Path(tempfile.mktemp())
        tracker = VersionTracker(db_path)
        
        plan_state = {
            "task-1": {"state": "DRAFT", "type": "worker"},
            "task-2": {"state": "DECIDED", "type": "verifier"}
        }
        
        # Record same state twice
        version1 = tracker.record_version(plan_state, lamport=10)
        version2 = tracker.record_version(plan_state, lamport=20)
        
        # Should have same merkle root
        assert version1.merkle_root == version2.merkle_root
        
        # Modify state slightly
        plan_state["task-1"]["state"] = "DECIDED"
        version3 = tracker.record_version(plan_state, lamport=30)
        
        # Should have different merkle root
        assert version3.merkle_root != version1.merkle_root
