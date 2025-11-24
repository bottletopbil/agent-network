"""
Plan Store: append-only op-log with CRDT semantics.

Tables:
- ops: All plan operations (never deleted)
- tasks: Derived view of current task state
- edges: Derived dependency graph
"""

import sqlite3
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class OpType(Enum):
    ADD_TASK = "ADD_TASK"
    REQUIRES = "REQUIRES"
    PRODUCES = "PRODUCES"
    STATE = "STATE"
    LINK = "LINK"
    ANNOTATE = "ANNOTATE"


class TaskState(Enum):
    DRAFT = "DRAFT"
    DECIDED = "DECIDED"
    VERIFIED = "VERIFIED"
    FINAL = "FINAL"


@dataclass
class PlanOp:
    """Single operation in the plan log"""
    op_id: str          # UUID
    thread_id: str
    lamport: int
    actor_id: str       # Public key
    op_type: OpType
    task_id: str        # Subject of operation
    payload: Dict[str, Any]
    timestamp_ns: int


class PlanStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()
    
    def _init_schema(self):
        with self.conn:
            # Op log (append-only)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ops (
                    op_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    lamport INTEGER NOT NULL,
                    actor_id TEXT NOT NULL,
                    op_type TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp_ns INTEGER NOT NULL
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_thread ON ops(thread_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_lamport ON ops(lamport)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_task ON ops(task_id)")
            
            # Derived task view
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    task_type TEXT,
                    state TEXT NOT NULL DEFAULT 'DRAFT',
                    last_lamport INTEGER NOT NULL
                )
            """)
            
            # Derived edges
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    PRIMARY KEY (parent_id, child_id)
                )
            """)
    
    def append_op(self, op: PlanOp) -> None:
        """Append operation and update derived views"""
        with self.lock:
            with self.conn:
                # Insert op
                self.conn.execute("""
                    INSERT INTO ops 
                    (op_id, thread_id, lamport, actor_id, op_type, task_id, payload_json, timestamp_ns)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    op.op_id, op.thread_id, op.lamport, op.actor_id,
                    op.op_type.value, op.task_id, json.dumps(op.payload), op.timestamp_ns
                ))
                
                # Update derived views
                self._apply_op(op)
    
    def _apply_op(self, op: PlanOp):
        """Update derived tables based on op type"""
        if op.op_type == OpType.ADD_TASK:
            self.conn.execute("""
                INSERT OR IGNORE INTO tasks (task_id, thread_id, task_type, last_lamport)
                VALUES (?, ?, ?, ?)
            """, (op.task_id, op.thread_id, op.payload.get("type"), op.lamport))
        
        elif op.op_type == OpType.STATE:
            # Ensure task exists (create if needed)
            self.conn.execute("""
                INSERT OR IGNORE INTO tasks (task_id, thread_id, task_type, last_lamport)
                VALUES (?, ?, NULL, 0)
            """, (op.task_id, op.thread_id))
            
            # Monotonic: only advance if lamport is newer
            new_state = op.payload["state"]
            self.conn.execute("""
                UPDATE tasks 
                SET state = ?, last_lamport = ?
                WHERE task_id = ? AND last_lamport < ?
            """, (new_state, op.lamport, op.task_id, op.lamport))
        
        elif op.op_type == OpType.LINK:
            parent = op.payload["parent"]
            child = op.payload["child"]
            self.conn.execute("""
                INSERT OR IGNORE INTO edges (parent_id, child_id)
                VALUES (?, ?)
            """, (parent, child))
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get current task state"""
        cursor = self.conn.execute("""
            SELECT task_id, thread_id, task_type, state
            FROM tasks WHERE task_id = ?
        """, (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "task_id": row[0],
            "thread_id": row[1],
            "task_type": row[2],
            "state": row[3]
        }
    
    def get_ops_for_thread(self, thread_id: str) -> List[PlanOp]:
        """Get all ops for a thread, ordered by lamport"""
        cursor = self.conn.execute("""
            SELECT op_id, thread_id, lamport, actor_id, op_type, task_id, payload_json, timestamp_ns
            FROM ops
            WHERE thread_id = ?
            ORDER BY lamport ASC
        """, (thread_id,))
        
        ops = []
        for row in cursor:
            ops.append(PlanOp(
                op_id=row[0],
                thread_id=row[1],
                lamport=row[2],
                actor_id=row[3],
                op_type=OpType(row[4]),
                task_id=row[5],
                payload=json.loads(row[6]),
                timestamp_ns=row[7]
            ))
        return ops
