#!/usr/bin/env python3
"""
Migration Tool: SQLite PlanStore → Automerge CRDT Store

Migrates existing plan data from SQLite-based storage to the new
Automerge CRDT format, with verification and reporting.

Usage:
    python tools/migrate_to_automerge.py \
        --sqlite-db .state/plan.db \
        --output automerge_plan.bin \
        --verify
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plan_store import PlanStore, PlanOp, OpType, TaskState
from plan.automerge_store import AutomergePlanStore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class MigrationTool:
    """
    Migrates plan data from SQLite to Automerge CRDT format.
    
    Provides:
    - Loading ops from SQLite
    - Exporting to Automerge format
    - Verification of migration correctness
    """
    
    def __init__(self):
        self.sqlite_store: Optional[PlanStore] = None
        self.automerge_store: Optional[AutomergePlanStore] = None
    
    def load_from_sqlite(self, db_path: Path) -> List[PlanOp]:
        """
        Load all operations from SQLite PlanStore.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            List of PlanOp objects in lamport order
        """
        logger.info(f"Loading ops from SQLite: {db_path}")
        
        if not db_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {db_path}")
        
        # Open SQLite store
        self.sqlite_store = PlanStore(db_path)
        
        # Get all ops from all threads
        all_ops = []
        
        # Query unique thread IDs
        cursor = self.sqlite_store.conn.execute(
            "SELECT DISTINCT thread_id FROM ops"
        )
        thread_ids = [row[0] for row in cursor]
        
        # Get ops for each thread
        for thread_id in thread_ids:
            thread_ops = self.sqlite_store.get_ops_for_thread(thread_id)
            all_ops.extend(thread_ops)
        
        # Sort by lamport for deterministic replay
        all_ops.sort(key=lambda op: op.lamport)
        
        logger.info(f"Loaded {len(all_ops)} ops from {len(thread_ids)} threads")
        
        return all_ops
    
    def export_to_automerge(
        self, 
        ops: List[PlanOp], 
        output_path: Path
    ) -> AutomergePlanStore:
        """
        Export ops to Automerge CRDT store.
        
        Args:
            ops: List of operations to export
            output_path: Path to save Automerge store
            
        Returns:
            AutomergePlanStore with all ops applied
        """
        logger.info(f"Exporting {len(ops)} ops to Automerge")
        
        # Create new Automerge store
        self.automerge_store = AutomergePlanStore()
        
        # Replay all ops in order
        for i, op in enumerate(ops):
            self.automerge_store.append_op(op)
            
            if (i + 1) % 100 == 0:
                logger.debug(f"Processed {i + 1}/{len(ops)} ops")
        
        # Save to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.automerge_store.get_save_data()
        
        with open(output_path, 'wb') as f:
            f.write(data)
        
        logger.info(f"Saved Automerge store to {output_path} ({len(data)} bytes)")
        
        return self.automerge_store
    
    def verify_migration(
        self, 
        sqlite_path: Path, 
        automerge_path: Path
    ) -> Tuple[bool, Dict]:
        """
        Verify migration correctness by comparing stores.
        
        Args:
            sqlite_path: Path to SQLite database
            automerge_path: Path to Automerge store
            
        Returns:
            (success: bool, report: Dict with comparison details)
        """
        logger.info("Verifying migration...")
        
        # Load SQLite store if not already loaded
        if not self.sqlite_store:
            self.sqlite_store = PlanStore(sqlite_path)
        
        # Load Automerge store
        self.automerge_store = AutomergePlanStore()
        with open(automerge_path, 'rb') as f:
            self.automerge_store.load_from_data(f.read())
        
        report = {
            "success": True,
            "errors": [],
            "warnings": [],
            "statistics": {}
        }
        
        # Compare task counts
        sqlite_tasks = self._get_sqlite_tasks()
        automerge_tasks = self.automerge_store.get_all_tasks()
        
        sqlite_task_ids = set(sqlite_tasks.keys())
        automerge_task_ids = set(t["task_id"] for t in automerge_tasks)
        
        report["statistics"]["sqlite_tasks"] = len(sqlite_task_ids)
        report["statistics"]["automerge_tasks"] = len(automerge_task_ids)
        
        # Check for missing tasks
        missing_in_automerge = sqlite_task_ids - automerge_task_ids
        extra_in_automerge = automerge_task_ids - sqlite_task_ids
        
        if missing_in_automerge:
            report["errors"].append(
                f"Missing {len(missing_in_automerge)} tasks in Automerge: "
                f"{list(missing_in_automerge)[:5]}"
            )
            report["success"] = False
        
        if extra_in_automerge:
            report["warnings"].append(
                f"Extra {len(extra_in_automerge)} tasks in Automerge: "
                f"{list(extra_in_automerge)[:5]}"
            )
        
        # Compare task states for common tasks
        common_tasks = sqlite_task_ids & automerge_task_ids
        state_mismatches = []
        
        for task_id in common_tasks:
            sqlite_task = sqlite_tasks[task_id]
            automerge_task = self.automerge_store.get_task(task_id)
            
            if sqlite_task["state"] != automerge_task["state"]:
                state_mismatches.append({
                    "task_id": task_id,
                    "sqlite_state": sqlite_task["state"],
                    "automerge_state": automerge_task["state"]
                })
        
        report["statistics"]["state_mismatches"] = len(state_mismatches)
        
        if state_mismatches:
            report["errors"].append(
                f"State mismatches in {len(state_mismatches)} tasks: "
                f"{state_mismatches[:3]}"
            )
            report["success"] = False
        
        # Compare edges
        sqlite_edges = self._get_sqlite_edges()
        automerge_edges = self.automerge_store.doc.edges
        
        report["statistics"]["sqlite_edges"] = sum(
            len(children) for children in sqlite_edges.values()
        )
        report["statistics"]["automerge_edges"] = sum(
            len(children) for children in automerge_edges.values()
        )
        
        # Log summary
        if report["success"]:
            logger.info("✓ Migration verified successfully")
            logger.info(f"  Tasks: {report['statistics']['automerge_tasks']}")
            logger.info(f"  Edges: {report['statistics']['automerge_edges']}")
        else:
            logger.error("✗ Migration verification failed")
            for error in report["errors"]:
                logger.error(f"  - {error}")
        
        if report["warnings"]:
            for warning in report["warnings"]:
                logger.warning(f"  - {warning}")
        
        return report["success"], report
    
    def _get_sqlite_tasks(self) -> Dict:
        """Get all tasks from SQLite store"""
        tasks = {}
        cursor = self.sqlite_store.conn.execute(
            "SELECT task_id, thread_id, task_type, state FROM tasks"
        )
        for row in cursor:
            tasks[row[0]] = {
                "task_id": row[0],
                "thread_id": row[1],
                "task_type": row[2],
                "state": row[3]
            }
        return tasks
    
    def _get_sqlite_edges(self) -> Dict[str, List[str]]:
        """Get all edges from SQLite store"""
        edges = {}
        cursor = self.sqlite_store.conn.execute(
            "SELECT parent_id, child_id FROM edges"
        )
        for row in cursor:
            parent, child = row
            if parent not in edges:
                edges[parent] = []
            edges[parent].append(child)
        return edges
    
    def generate_report(self, report: Dict) -> str:
        """
        Generate human-readable migration report.
        
        Args:
            report: Report dict from verify_migration
            
        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 60)
        lines.append("MIGRATION REPORT")
        lines.append("=" * 60)
        
        lines.append(f"\nStatus: {'SUCCESS ✓' if report['success'] else 'FAILED ✗'}")
        
        lines.append("\nStatistics:")
        for key, value in report["statistics"].items():
            lines.append(f"  {key}: {value}")
        
        if report["errors"]:
            lines.append("\nErrors:")
            for error in report["errors"]:
                lines.append(f"  - {error}")
        
        if report["warnings"]:
            lines.append("\nWarnings:")
            for warning in report["warnings"]:
                lines.append(f"  - {warning}")
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)


def main():
    """Command-line interface for migration tool"""
    parser = argparse.ArgumentParser(
        description="Migrate SQLite PlanStore to Automerge CRDT format"
    )
    
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        required=True,
        help="Path to SQLite database (e.g., .state/plan.db)"
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for Automerge store (e.g., automerge_plan.bin)"
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration after export"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run migration
    tool = MigrationTool()
    
    try:
        # Load from SQLite
        ops = tool.load_from_sqlite(args.sqlite_db)
        
        # Export to Automerge
        tool.export_to_automerge(ops, args.output)
        
        # Verify if requested
        if args.verify:
            success, report = tool.verify_migration(args.sqlite_db, args.output)
            print(tool.generate_report(report))
            
            sys.exit(0 if success else 1)
        else:
            logger.info("Migration complete (verification skipped)")
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
