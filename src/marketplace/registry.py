"""
Agent Registry for Marketplace

Manages agent registration, discovery, and statistics tracking.
"""

import sqlite3
import json
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class AgentStatus(Enum):
    """Agent registration status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


@dataclass
class AgentStats:
    """Statistics for an agent"""
    agent_id: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float
    avg_response_time_ms: float
    total_earnings: float
    reputation_score: float
    last_active: float
    uptime_percentage: float


@dataclass
class SearchFilters:
    """Filters for agent search"""
    capabilities: Optional[List[str]] = None
    min_reputation: Optional[float] = None
    max_price: Optional[float] = None
    status: Optional[AgentStatus] = None
    tags: Optional[List[str]] = None


class AgentRegistry:
    """
    Agent Registry for marketplace.
    
    Manages agent registration, manifest updates, discovery, and stats.
    """
    
    def __init__(self, db_path: Path):
        """
        Initialize registry.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        cursor = self.conn.cursor()
        
        # Agent registrations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_registrations (
                registration_id TEXT PRIMARY KEY,
                agent_id TEXT UNIQUE NOT NULL,
                manifest JSON NOT NULL,
                stake REAL NOT NULL,
                status TEXT NOT NULL,
                registered_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        
        # Agent capabilities table (for efficient searching)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_capabilities (
                agent_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                PRIMARY KEY (agent_id, capability),
                FOREIGN KEY (agent_id) REFERENCES agent_registrations(agent_id)
            )
        """)
        
        # Agent tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_tags (
                agent_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (agent_id, tag),
                FOREIGN KEY (agent_id) REFERENCES agent_registrations(agent_id)
            )
        """)
        
        # Agent statistics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_stats (
                agent_id TEXT PRIMARY KEY,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                total_response_time_ms REAL DEFAULT 0,
                total_earnings REAL DEFAULT 0,
                reputation_score REAL DEFAULT 0.8,
                last_active REAL,
                total_uptime_seconds REAL DEFAULT 0,
                FOREIGN KEY (agent_id) REFERENCES agent_registrations(agent_id)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_status ON agent_registrations(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_capability ON agent_capabilities(capability)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag ON agent_tags(tag)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reputation ON agent_stats(reputation_score)")
        
        self.conn.commit()
    
    def register_agent(
        self,
        agent_id: str,
        manifest: Dict[str, Any],
        stake: float
    ) -> str:
        """
        Register a new agent.
        
        Args:
            agent_id: Unique agent identifier (DID)
            manifest: Agent manifest with capabilities, pricing, etc.
            stake: Stake amount in credits
        
        Returns:
            Registration ID
        
        Raises:
            ValueError: If agent already registered or invalid data
        """
        # Validate manifest
        required_fields = ["capabilities", "pricing"]
        for field in required_fields:
            if field not in manifest:
                raise ValueError(f"Manifest missing required field: {field}")
        
        # Check if agent already registered
        cursor = self.conn.cursor()
        existing = cursor.execute(
            "SELECT agent_id FROM agent_registrations WHERE agent_id = ?",
            (agent_id,)
        ).fetchone()
        
        if existing:
            raise ValueError(f"Agent {agent_id} already registered")
        
        # Generate registration ID
        registration_id = str(uuid.uuid4())
        now = time.time()
        
        # Insert registration
        cursor.execute("""
            INSERT INTO agent_registrations 
            (registration_id, agent_id, manifest, stake, status, registered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            registration_id,
            agent_id,
            json.dumps(manifest),
            stake,
            AgentStatus.ACTIVE.value,
            now,
            now
        ))
        
        # Insert capabilities
        capabilities = manifest.get("capabilities", [])
        for capability in capabilities:
            cursor.execute("""
                INSERT INTO agent_capabilities (agent_id, capability)
                VALUES (?, ?)
            """, (agent_id, capability))
        
        # Insert tags
        tags = manifest.get("tags", [])
        for tag in tags:
            cursor.execute("""
                INSERT INTO agent_tags (agent_id, tag)
                VALUES (?, ?)
            """, (agent_id, tag))
        
        # Initialize stats
        cursor.execute("""
            INSERT INTO agent_stats (agent_id, last_active)
            VALUES (?, ?)
        """, (agent_id, now))
        
        self.conn.commit()
        
        return registration_id
    
    def update_manifest(
        self,
        agent_id: str,
        manifest: Dict[str, Any]
    ) -> bool:
        """
        Update agent manifest.
        
        Args:
            agent_id: Agent identifier
            manifest: Updated manifest
        
        Returns:
            True if successful
        
        Raises:
            ValueError: If agent not found
        """
        cursor = self.conn.cursor()
        
        # Check if agent exists
        existing = cursor.execute(
            "SELECT agent_id FROM agent_registrations WHERE agent_id = ?",
            (agent_id,)
        ).fetchone()
        
        if not existing:
            raise ValueError(f"Agent {agent_id} not found")
        
        # Update manifest
        cursor.execute("""
            UPDATE agent_registrations
            SET manifest = ?, updated_at = ?
            WHERE agent_id = ?
        """, (json.dumps(manifest), time.time(), agent_id))
        
        # Update capabilities
        cursor.execute("DELETE FROM agent_capabilities WHERE agent_id = ?", (agent_id,))
        capabilities = manifest.get("capabilities", [])
        for capability in capabilities:
            cursor.execute("""
                INSERT INTO agent_capabilities (agent_id, capability)
                VALUES (?, ?)
            """, (agent_id, capability))
        
        # Update tags
        cursor.execute("DELETE FROM agent_tags WHERE agent_id = ?", (agent_id,))
        tags = manifest.get("tags", [])
        for tag in tags:
            cursor.execute("""
                INSERT INTO agent_tags (agent_id, tag)
                VALUES (?, ?)
            """, (agent_id, tag))
        
        self.conn.commit()
        
        return True
    
    def search_agents(
        self,
        capabilities: Optional[List[str]] = None,
        filters: Optional[SearchFilters] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for agents by capabilities and filters.
        
        Args:
            capabilities: Required capabilities (AND logic)
            filters: Additional search filters
        
        Returns:
            List of matching agent records
        """
        cursor = self.conn.cursor()
        
        # Build query
        query = """
            SELECT DISTINCT r.agent_id, r.manifest, r.stake, r.status, 
                   r.registered_at, r.updated_at,
                   s.reputation_score, s.total_tasks, s.completed_tasks
            FROM agent_registrations r
            LEFT JOIN agent_stats s ON r.agent_id = s.agent_id
            WHERE 1=1
        """
        params = []
        
        # Filter by capabilities
        if capabilities:
            placeholders = ",".join("?" * len(capabilities))
            query += f"""
                AND r.agent_id IN (
                    SELECT agent_id 
                    FROM agent_capabilities
                    WHERE capability IN ({placeholders})
                    GROUP BY agent_id
                    HAVING COUNT(DISTINCT capability) = ?
                )
            """
            params.extend(capabilities)
            params.append(len(capabilities))
        
        # Apply filters
        if filters:
            if filters.min_reputation is not None:
                query += " AND s.reputation_score >= ?"
                params.append(filters.min_reputation)
            
            if filters.status is not None:
                query += " AND r.status = ?"
                params.append(filters.status.value)
            
            if filters.tags:
                placeholders = ",".join("?" * len(filters.tags))
                query += f"""
                    AND r.agent_id IN (
                        SELECT agent_id
                        FROM agent_tags
                        WHERE tag IN ({placeholders})
                    )
                """
                params.extend(filters.tags)
        
        # Order by reputation
        query += " ORDER BY s.reputation_score DESC, r.registered_at DESC"
        
        # Execute query
        rows = cursor.execute(query, params).fetchall()
        
        # Convert to dictionaries
        results = []
        for row in rows:
            results.append({
                "agent_id": row["agent_id"],
                "manifest": json.loads(row["manifest"]),
                "stake": row["stake"],
                "status": row["status"],
                "registered_at": row["registered_at"],
                "updated_at": row["updated_at"],
                "reputation_score": row["reputation_score"],
                "total_tasks": row["total_tasks"],
                "completed_tasks": row["completed_tasks"]
            })
        
        return results
    
    def get_agent_stats(self, agent_id: str) -> Optional[AgentStats]:
        """
        Get statistics for an agent.
        
        Args:
            agent_id: Agent identifier
        
        Returns:
            AgentStats or None if not found
        """
        cursor = self.conn.cursor()
        
        row = cursor.execute("""
            SELECT 
                agent_id,
                total_tasks,
                completed_tasks,
                failed_tasks,
                total_response_time_ms,
                total_earnings,
                reputation_score,
                last_active,
                total_uptime_seconds
            FROM agent_stats
            WHERE agent_id = ?
        """, (agent_id,)).fetchone()
        
        if not row:
            return None
        
        # Calculate derived stats
        success_rate = 0.0
        if row["total_tasks"] > 0:
            success_rate = row["completed_tasks"] / row["total_tasks"]
        
        avg_response_time = 0.0
        if row["completed_tasks"] > 0:
            avg_response_time = row["total_response_time_ms"] / row["completed_tasks"]
        
        # Calculate uptime percentage (estimate based on time since registration)
        registration = cursor.execute(
            "SELECT registered_at FROM agent_registrations WHERE agent_id = ?",
            (agent_id,)
        ).fetchone()
        
        uptime_percentage = 0.0
        if registration:
            total_time = time.time() - registration["registered_at"]
            if total_time > 0:
                uptime_percentage = min(100.0, (row["total_uptime_seconds"] / total_time) * 100)
        
        return AgentStats(
            agent_id=row["agent_id"],
            total_tasks=row["total_tasks"],
            completed_tasks=row["completed_tasks"],
            failed_tasks=row["failed_tasks"],
            success_rate=success_rate,
            avg_response_time_ms=avg_response_time,
            total_earnings=row["total_earnings"],
            reputation_score=row["reputation_score"],
            last_active=row["last_active"],
            uptime_percentage=uptime_percentage
        )
    
    def record_task_completion(
        self,
        agent_id: str,
        success: bool,
        response_time_ms: float,
        earnings: float = 0.0
    ):
        """
        Record task completion for stats tracking.
        
        Args:
            agent_id: Agent identifier
            success: Whether task succeeded
            response_time_ms: Response time in milliseconds
            earnings: Amount earned
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            UPDATE agent_stats
            SET total_tasks = total_tasks + 1,
                completed_tasks = completed_tasks + ?,
                failed_tasks = failed_tasks + ?,
                total_response_time_ms = total_response_time_ms + ?,
                total_earnings = total_earnings + ?,
                last_active = ?
            WHERE agent_id = ?
        """, (
            1 if success else 0,
            0 if success else 1,
            response_time_ms if success else 0,
            earnings,
            time.time(),
            agent_id
        ))
        
        self.conn.commit()
    
    def update_reputation(self, agent_id: str, new_reputation: float):
        """Update agent reputation score"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE agent_stats
            SET reputation_score = ?
            WHERE agent_id = ?
        """, (new_reputation, agent_id))
        self.conn.commit()
    
    def set_agent_status(self, agent_id: str, status: AgentStatus):
        """Update agent status"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE agent_registrations
            SET status = ?, updated_at = ?
            WHERE agent_id = ?
        """, (status.value, time.time(), agent_id))
        self.conn.commit()
