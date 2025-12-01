"""
Task Marketplace

Manages task listings, bid tracking, price analytics, and agent ratings.
"""

import sqlite3
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict


class TaskStatus(Enum):
    """Task status in marketplace"""

    OPEN = "open"
    BIDDING = "bidding"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Task in marketplace"""

    task_id: str
    description: str
    capabilities_required: List[str]
    budget: float
    deadline: Optional[float]
    status: TaskStatus
    poster_id: str
    created_at: float
    assigned_to: Optional[str] = None


@dataclass
class Bid:
    """Bid on a task"""

    bid_id: str
    task_id: str
    agent_id: str
    amount: float
    estimated_time: float
    message: str
    created_at: float
    status: str  # pending, accepted, rejected


@dataclass
class PriceTrend:
    """Price trend analytics"""

    capability: str
    avg_price: float
    min_price: float
    max_price: float
    total_tasks: int
    trend_direction: str  # up, down, stable


@dataclass
class AgentRating:
    """Agent rating"""

    agent_id: str
    rater_id: str
    rating: float
    comment: str
    created_at: float


class TaskMarketplace:
    """
    Task Marketplace for agent economy.

    Manages task listings, bid tracking, price analytics, and ratings.
    """

    def __init__(self, db_path: Path):
        """
        Initialize marketplace.

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

        # Tasks table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                capabilities_required JSON NOT NULL,
                budget REAL NOT NULL,
                deadline REAL,
                status TEXT NOT NULL,
                poster_id TEXT NOT NULL,
                assigned_to TEXT,
                created_at REAL NOT NULL
            )
        """
        )

        # Bids table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bids (
                bid_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                amount REAL NOT NULL,
                estimated_time REAL NOT NULL,
                message TEXT,
                created_at REAL NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """
        )

        # Agent ratings table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                rater_id TEXT NOT NULL,
                rating REAL NOT NULL,
                comment TEXT,
                created_at REAL NOT NULL
            )
        """
        )

        # Price history for analytics
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT NOT NULL,
                price REAL NOT NULL,
                recorded_at REAL NOT NULL
            )
        """
        )

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bid_task ON bids(task_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bid_agent ON bids(agent_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rating_agent ON agent_ratings(agent_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_capability ON price_history(capability)"
        )

        self.conn.commit()

    def post_task(
        self,
        task_id: str,
        description: str,
        capabilities_required: List[str],
        budget: float,
        poster_id: str,
        deadline: Optional[float] = None,
    ) -> str:
        """
        Post a new task to marketplace.

        Args:
            task_id: Unique task identifier
            description: Task description
            capabilities_required: Required agent capabilities
            budget: Maximum budget for task
            poster_id: ID of task poster
            deadline: Optional deadline timestamp

        Returns:
            Task ID
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO tasks 
            (task_id, description, capabilities_required, budget, deadline, 
             status, poster_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_id,
                description,
                json.dumps(capabilities_required),
                budget,
                deadline,
                TaskStatus.OPEN.value,
                poster_id,
                time.time(),
            ),
        )

        # Record price for analytics
        for capability in capabilities_required:
            cursor.execute(
                """
                INSERT INTO price_history (capability, price, recorded_at)
                VALUES (?, ?, ?)
            """,
                (capability, budget, time.time()),
            )

        self.conn.commit()

        return task_id

    def list_available_tasks(
        self,
        capabilities: Optional[List[str]] = None,
        max_budget: Optional[float] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[Dict[str, Any]]:
        """
        List available tasks in marketplace.

        Args:
            capabilities: Filter by required capabilities
            max_budget: Maximum budget filter
            status: Filter by status (defaults to OPEN)

        Returns:
            List of task dictionaries
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        # Default to open tasks
        if status is None:
            query += " AND status = ?"
            params.append(TaskStatus.OPEN.value)
        else:
            query += " AND status = ?"
            params.append(status.value)

        # Filter by budget
        if max_budget is not None:
            query += " AND budget <= ?"
            params.append(max_budget)

        query += " ORDER BY created_at DESC"

        rows = cursor.execute(query, params).fetchall()

        tasks = []
        for row in rows:
            task_caps = json.loads(row["capabilities_required"])

            # Filter by capabilities if specified
            if capabilities:
                if not all(cap in task_caps for cap in capabilities):
                    continue

            tasks.append(
                {
                    "task_id": row["task_id"],
                    "description": row["description"],
                    "capabilities_required": task_caps,
                    "budget": row["budget"],
                    "deadline": row["deadline"],
                    "status": row["status"],
                    "poster_id": row["poster_id"],
                    "assigned_to": row["assigned_to"],
                    "created_at": row["created_at"],
                }
            )

        return tasks

    def submit_bid(
        self,
        bid_id: str,
        task_id: str,
        agent_id: str,
        amount: float,
        estimated_time: float,
        message: str = "",
    ) -> str:
        """
        Submit a bid for a task.

        Args:
            bid_id: Unique bid identifier
            task_id: Task being bid on
            agent_id: Agent submitting bid
            amount: Bid amount
            estimated_time: Estimated completion time
            message: Optional message/proposal

        Returns:
            Bid ID
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO bids 
            (bid_id, task_id, agent_id, amount, estimated_time, message, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                bid_id,
                task_id,
                agent_id,
                amount,
                estimated_time,
                message,
                time.time(),
                "pending",
            ),
        )

        # Update task status to bidding
        cursor.execute(
            """
            UPDATE tasks SET status = ? WHERE task_id = ?
        """,
            (TaskStatus.BIDDING.value, task_id),
        )

        self.conn.commit()

        return bid_id

    def get_bid_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get bid history for a task.

        Args:
            task_id: Task identifier

        Returns:
            List of bids ordered by amount (lowest first)
        """
        cursor = self.conn.cursor()

        rows = cursor.execute(
            """
            SELECT * FROM bids
            WHERE task_id = ?
            ORDER BY amount ASC, created_at ASC
        """,
            (task_id,),
        ).fetchall()

        bids = []
        for row in rows:
            bids.append(
                {
                    "bid_id": row["bid_id"],
                    "task_id": row["task_id"],
                    "agent_id": row["agent_id"],
                    "amount": row["amount"],
                    "estimated_time": row["estimated_time"],
                    "message": row["message"],
                    "created_at": row["created_at"],
                    "status": row["status"],
                }
            )

        return bids

    def accept_bid(self, bid_id: str) -> bool:
        """Accept a bid and assign task"""
        cursor = self.conn.cursor()

        # Get bid details
        bid = cursor.execute(
            "SELECT task_id, agent_id FROM bids WHERE bid_id = ?", (bid_id,)
        ).fetchone()

        if not bid:
            return False

        # Update bid status
        cursor.execute(
            """
            UPDATE bids SET status = ?
            WHERE bid_id = ?
        """,
            ("accepted", bid_id),
        )

        # Reject other bids
        cursor.execute(
            """
            UPDATE bids SET status = ?
            WHERE task_id = ? AND bid_id != ?
        """,
            ("rejected", bid["task_id"], bid_id),
        )

        # Assign task
        cursor.execute(
            """
            UPDATE tasks 
            SET status = ?, assigned_to = ?
            WHERE task_id = ?
        """,
            (TaskStatus.ASSIGNED.value, bid["agent_id"], bid["task_id"]),
        )

        self.conn.commit()

        return True

    def track_price_trends(
        self, capability: Optional[str] = None, days: int = 30
    ) -> List[PriceTrend]:
        """
        Track price trends for capabilities.

        Args:
            capability: Specific capability (None for all)
            days: Number of days to analyze

        Returns:
            List of price trends
        """
        cursor = self.conn.cursor()

        cutoff = time.time() - (days * 24 * 3600)

        if capability:
            query = """
                SELECT 
                    capability,
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    COUNT(*) as total_tasks
                FROM price_history
                WHERE capability = ? AND recorded_at > ?
                GROUP BY capability
            """
            params = (capability, cutoff)
        else:
            query = """
                SELECT 
                    capability,
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    COUNT(*) as total_tasks
                FROM price_history
                WHERE recorded_at > ?
                GROUP BY capability
            """
            params = (cutoff,)

        rows = cursor.execute(query, params).fetchall()

        trends = []
        for row in rows:
            # Calculate trend direction (simplified)
            trend_direction = "stable"
            if row["max_price"] > row["avg_price"] * 1.2:
                trend_direction = "up"
            elif row["min_price"] < row["avg_price"] * 0.8:
                trend_direction = "down"

            trends.append(
                PriceTrend(
                    capability=row["capability"],
                    avg_price=row["avg_price"],
                    min_price=row["min_price"],
                    max_price=row["max_price"],
                    total_tasks=row["total_tasks"],
                    trend_direction=trend_direction,
                )
            )

        return trends

    def rate_agent(
        self, agent_id: str, rater_id: str, rating: float, comment: str = ""
    ) -> int:
        """
        Rate an agent.

        Args:
            agent_id: Agent being rated
            rater_id: User submitting rating
            rating: Rating value (0.0-5.0)
            comment: Optional comment

        Returns:
            Rating ID

        Raises:
            ValueError: If rating out of range
        """
        if not 0.0 <= rating <= 5.0:
            raise ValueError("Rating must be between 0.0 and 5.0")

        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO agent_ratings (agent_id, rater_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (agent_id, rater_id, rating, comment, time.time()),
        )

        self.conn.commit()

        return cursor.lastrowid

    def get_agent_ratings(self, agent_id: str) -> Dict[str, Any]:
        """
        Get agent ratings summary.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with rating statistics
        """
        cursor = self.conn.cursor()

        row = cursor.execute(
            """
            SELECT 
                COUNT(*) as total_ratings,
                AVG(rating) as avg_rating,
                MIN(rating) as min_rating,
                MAX(rating) as max_rating
            FROM agent_ratings
            WHERE agent_id = ?
        """,
            (agent_id,),
        ).fetchone()

        # Get recent ratings
        recent = cursor.execute(
            """
            SELECT rating, rater_id, comment, created_at
            FROM agent_ratings
            WHERE agent_id = ?
            ORDER BY created_at DESC
            LIMIT 10
        """,
            (agent_id,),
        ).fetchall()

        return {
            "agent_id": agent_id,
            "total_ratings": row["total_ratings"],
            "avg_rating": row["avg_rating"] if row["avg_rating"] else 0.0,
            "min_rating": row["min_rating"] if row["min_rating"] else 0.0,
            "max_rating": row["max_rating"] if row["max_rating"] else 0.0,
            "recent_ratings": [
                {
                    "rating": r["rating"],
                    "rater_id": r["rater_id"],
                    "comment": r["comment"],
                    "created_at": r["created_at"],
                }
                for r in recent
            ],
        }

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get agent leaderboard by average rating.

        Args:
            limit: Number of top agents to return

        Returns:
            List of agents with ratings
        """
        cursor = self.conn.cursor()

        rows = cursor.execute(
            """
            SELECT 
                agent_id,
                COUNT(*) as total_ratings,
                AVG(rating) as avg_rating
            FROM agent_ratings
            GROUP BY agent_id
            HAVING COUNT(*) >= 3
            ORDER BY avg_rating DESC, total_ratings DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

        leaderboard = []
        for i, row in enumerate(rows, 1):
            leaderboard.append(
                {
                    "rank": i,
                    "agent_id": row["agent_id"],
                    "avg_rating": row["avg_rating"],
                    "total_ratings": row["total_ratings"],
                }
            )

        return leaderboard
