"""
Test SQLite to Automerge Migration Tool

Verifies:
- Export of all ops from SQLite
- Task equivalence between stores
- Edge equivalence
- Annotation equivalence
- Full migration pipeline
"""

import pytest
import sys
from pathlib import Path
import tempfile
import uuid
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plan_store import PlanStore, PlanOp, OpType
from plan.automerge_store import AutomergePlanStore

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from migrate_to_automerge import MigrationTool


def create_test_op(
    op_type: OpType,
    task_id: str,
    lamport: int,
    thread_id: str = "test-thread",
    actor_id: str = "test-actor",
    payload: dict = None,
) -> PlanOp:
    """Helper to create test operations"""
    return PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=lamport,
        actor_id=actor_id,
        op_type=op_type,
        task_id=task_id,
        payload=payload or {},
        timestamp_ns=time.time_ns(),
    )


class TestExportAllOps:
    """Test exporting all ops from SQLite"""

    def test_export_all_ops(self):
        """All ops from SQLite are exported to Automerge"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"

            # Create SQLite store with ops
            sqlite_store = PlanStore(sqlite_path)

            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1, payload={"type": "build"}),
                create_test_op(OpType.ADD_TASK, "task-2", 2, payload={"type": "test"}),
                create_test_op(OpType.STATE, "task-1", 3, payload={"state": "DECIDED"}),
            ]

            for op in ops:
                sqlite_store.append_op(op)

            # Load ops using migration tool
            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)

            # Should have all 3 ops
            assert len(loaded_ops) == 3

            # Verify op order (by lamport)
            assert loaded_ops[0].lamport == 1
            assert loaded_ops[1].lamport == 2
            assert loaded_ops[2].lamport == 3

    def test_export_multiple_threads(self):
        """Ops from multiple threads are exported"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            sqlite_store = PlanStore(sqlite_path)

            # Add ops to different threads
            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1, thread_id="thread-a"),
                create_test_op(OpType.ADD_TASK, "task-2", 2, thread_id="thread-b"),
                create_test_op(OpType.ADD_TASK, "task-3", 3, thread_id="thread-a"),
            ]

            for op in ops:
                sqlite_store.append_op(op)

            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)

            # All ops should be loaded
            assert len(loaded_ops) == 3

            # Should include ops from both threads
            thread_ids = set(op.thread_id for op in loaded_ops)
            assert "thread-a" in thread_ids
            assert "thread-b" in thread_ids


class TestTaskEquivalence:
    """Test task equivalence between SQLite and Automerge"""

    def test_task_equivalence(self):
        """Tasks are equivalent after migration"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            # Create SQLite store
            sqlite_store = PlanStore(sqlite_path)

            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1, payload={"type": "build"}),
                create_test_op(OpType.ADD_TASK, "task-2", 2, payload={"type": "test"}),
                create_test_op(OpType.STATE, "task-1", 3, payload={"state": "DECIDED"}),
            ]

            for op in ops:
                sqlite_store.append_op(op)

            # Migrate to Automerge
            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            automerge_store = tool.export_to_automerge(loaded_ops, automerge_path)

            # Compare tasks
            sqlite_task1 = sqlite_store.get_task("task-1")
            automerge_task1 = automerge_store.get_task("task-1")

            assert sqlite_task1["task_id"] == automerge_task1["task_id"]
            assert sqlite_task1["state"] == automerge_task1["state"]
            assert sqlite_task1["task_type"] == automerge_task1["task_type"]

    def test_task_count_matches(self):
        """Task count matches between stores"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            sqlite_store = PlanStore(sqlite_path)

            # Create 10 tasks
            for i in range(10):
                op = create_test_op(OpType.ADD_TASK, f"task-{i}", i + 1, payload={"type": "test"})
                sqlite_store.append_op(op)

            # Migrate
            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            automerge_store = tool.export_to_automerge(loaded_ops, automerge_path)

            # Count should match
            assert len(automerge_store.doc.tasks) == 10


class TestEdgeEquivalence:
    """Test edge equivalence between stores"""

    def test_edge_equivalence(self):
        """Edges are preserved during migration"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            sqlite_store = PlanStore(sqlite_path)

            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1),
                create_test_op(OpType.ADD_TASK, "task-2", 2),
                create_test_op(OpType.ADD_TASK, "task-3", 3),
                create_test_op(
                    OpType.LINK,
                    "task-1",
                    4,
                    payload={"parent": "task-1", "child": "task-2"},
                ),
                create_test_op(
                    OpType.LINK,
                    "task-1",
                    5,
                    payload={"parent": "task-1", "child": "task-3"},
                ),
            ]

            for op in ops:
                sqlite_store.append_op(op)

            # Migrate
            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            automerge_store = tool.export_to_automerge(loaded_ops, automerge_path)

            # Verify edges
            children = automerge_store.get_edges("task-1")
            assert len(children) == 2
            assert "task-2" in children
            assert "task-3" in children


class TestAnnotationEquivalence:
    """Test annotation preservation"""

    def test_annotation_equivalence(self):
        """Annotations are preserved during migration"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            sqlite_store = PlanStore(sqlite_path)

            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1),
                create_test_op(
                    OpType.ANNOTATE,
                    "task-1",
                    2,
                    payload={"priority": "high", "owner": "alice"},
                ),
            ]

            for op in ops:
                sqlite_store.append_op(op)

            # Migrate
            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            automerge_store = tool.export_to_automerge(loaded_ops, automerge_path)

            # Verify annotations
            task = automerge_store.get_task("task-1")
            assert "annotations" in task
            assert task["annotations"]["priority"] == "high"
            assert task["annotations"]["owner"] == "alice"


class TestFullMigrationPipeline:
    """Test complete migration pipeline"""

    def test_full_migration_pipeline(self):
        """Complete migration from SQLite to Automerge with verification"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            # Create SQLite store with various ops
            sqlite_store = PlanStore(sqlite_path)

            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1, payload={"type": "build"}),
                create_test_op(OpType.ADD_TASK, "task-2", 2, payload={"type": "test"}),
                create_test_op(OpType.STATE, "task-1", 3, payload={"state": "DECIDED"}),
                create_test_op(
                    OpType.LINK,
                    "task-1",
                    4,
                    payload={"parent": "task-1", "child": "task-2"},
                ),
                create_test_op(OpType.ANNOTATE, "task-1", 5, payload={"priority": "high"}),
            ]

            for op in ops:
                sqlite_store.append_op(op)

            # Run full migration
            tool = MigrationTool()

            # Step 1: Load from SQLite
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            assert len(loaded_ops) == 5

            # Step 2: Export to Automerge
            tool.export_to_automerge(loaded_ops, automerge_path)
            assert automerge_path.exists()

            # Step 3: Verify migration
            success, report = tool.verify_migration(sqlite_path, automerge_path)

            assert success is True
            assert report["statistics"]["sqlite_tasks"] == 2
            assert report["statistics"]["automerge_tasks"] == 2
            assert len(report["errors"]) == 0

    def test_migration_verification_detects_differences(self):
        """Verification detects mismatches"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            # Create SQLite store
            sqlite_store = PlanStore(sqlite_path)
            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1),
                create_test_op(OpType.ADD_TASK, "task-2", 2),
            ]
            for op in ops:
                sqlite_store.append_op(op)

            # Create Automerge store with only one task (intentional mismatch)
            automerge_store = AutomergePlanStore()
            automerge_store.append_op(ops[0])  # Only task-1

            with open(automerge_path, "wb") as f:
                f.write(automerge_store.get_save_data())

            # Verify should fail
            tool = MigrationTool()
            success, report = tool.verify_migration(sqlite_path, automerge_path)

            assert success is False
            assert len(report["errors"]) > 0
            assert "Missing" in report["errors"][0]

    def test_file_persistence(self):
        """Migrated file can be loaded again"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "test.db"
            automerge_path = Path(tmpdir) / "test.bin"

            # Create and migrate
            sqlite_store = PlanStore(sqlite_path)
            ops = [
                create_test_op(OpType.ADD_TASK, "task-1", 1),
                create_test_op(OpType.STATE, "task-1", 2, payload={"state": "DECIDED"}),
            ]
            for op in ops:
                sqlite_store.append_op(op)

            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            tool.export_to_automerge(loaded_ops, automerge_path)

            # Load file in new store
            new_store = AutomergePlanStore()
            with open(automerge_path, "rb") as f:
                new_store.load_from_data(f.read())

            # Verify data
            task = new_store.get_task("task-1")
            assert task is not None
            assert task["state"] == "DECIDED"

    def test_generate_report(self):
        """Generate human-readable report"""
        tool = MigrationTool()

        report = {
            "success": True,
            "errors": [],
            "warnings": ["Some warning"],
            "statistics": {
                "sqlite_tasks": 10,
                "automerge_tasks": 10,
                "state_mismatches": 0,
            },
        }

        report_text = tool.generate_report(report)

        assert "SUCCESS ✓" in report_text
        assert "sqlite_tasks: 10" in report_text
        assert "Some warning" in report_text


class TestEmptyDatabase:
    """Test migration of empty database"""

    def test_empty_database_migration(self):
        """Can migrate empty database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "empty.db"
            automerge_path = Path(tmpdir) / "empty.bin"

            # Create empty store
            PlanStore(sqlite_path)

            # Migrate
            tool = MigrationTool()
            loaded_ops = tool.load_from_sqlite(sqlite_path)
            automerge_store = tool.export_to_automerge(loaded_ops, automerge_path)

            # Should have no ops or tasks
            assert len(loaded_ops) == 0
            assert len(automerge_store.doc.tasks) == 0

            # Verification should pass
            success, report = tool.verify_migration(sqlite_path, automerge_path)
            assert success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
