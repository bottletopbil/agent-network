"""
Challenge Window Management: Track time windows for submitting challenges.

Default challenge window is 24 hours after task finalization.
Windows can be extended when valid challenges are submitted.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass


# Default challenge window duration (24 hours in seconds)
DEFAULT_WINDOW_DURATION = 24 * 60 * 60  # 86400 seconds


@dataclass
class WindowInfo:
    """Information about a challenge window"""

    task_id: str
    opened_at_ns: int
    duration_seconds: int
    extended_count: int = 0

    def get_remaining_time(self) -> float:
        """
        Get remaining time in seconds.

        Returns:
            Remaining seconds (0 if expired)
        """
        elapsed_ns = time.time_ns() - self.opened_at_ns
        elapsed_seconds = elapsed_ns / 1e9
        remaining = self.duration_seconds - elapsed_seconds
        return max(0.0, remaining)

    def is_open(self) -> bool:
        """Check if window is still open"""
        return self.get_remaining_time() > 0


class ChallengeWindow:
    """
    Manages challenge windows for tasks.

    Each task gets a time window during which challenges can be submitted.
    Windows can be extended when valid challenges are received.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        """Initialize challenge window tracking table"""
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS challenge_windows (
                        task_id TEXT PRIMARY KEY,
                        opened_at_ns INTEGER NOT NULL,
                        duration_seconds INTEGER NOT NULL,
                        extended_count INTEGER DEFAULT 0,
                        created_at_ns INTEGER NOT NULL
                    )
                """
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_window_task ON challenge_windows(task_id)"
                )

    def create_window(self, task_id: str, duration: Optional[int] = None) -> WindowInfo:
        """
        Create a challenge window for a task.

        Args:
            task_id: Task identifier
            duration: Window duration in seconds (default: 24 hours)

        Returns:
            WindowInfo object
        """
        if duration is None:
            duration = DEFAULT_WINDOW_DURATION

        if duration <= 0:
            raise ValueError("Duration must be positive")

        opened_at_ns = time.time_ns()

        with self.lock:
            with self.conn:
                # Insert or replace window
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO challenge_windows
                    (task_id, opened_at_ns, duration_seconds, extended_count, created_at_ns)
                    VALUES (?, ?, ?, 0, ?)
                """,
                    (task_id, opened_at_ns, duration, opened_at_ns),
                )

        return WindowInfo(
            task_id=task_id,
            opened_at_ns=opened_at_ns,
            duration_seconds=duration,
            extended_count=0,
        )

    def get_window(self, task_id: str) -> Optional[WindowInfo]:
        """
        Get window information for a task.

        Args:
            task_id: Task identifier

        Returns:
            WindowInfo or None if no window exists
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT task_id, opened_at_ns, duration_seconds, extended_count
                FROM challenge_windows
                WHERE task_id = ?
            """,
                (task_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return WindowInfo(
                task_id=row[0],
                opened_at_ns=row[1],
                duration_seconds=row[2],
                extended_count=row[3],
            )

    def get_remaining_time(self, task_id: str) -> Optional[float]:
        """
        Get remaining time for a task's challenge window.

        Args:
            task_id: Task identifier

        Returns:
            Remaining seconds or None if no window exists
        """
        window = self.get_window(task_id)
        if not window:
            return None

        return window.get_remaining_time()

    def is_window_open(self, task_id: str) -> bool:
        """
        Check if challenge window is still open.

        Args:
            task_id: Task identifier

        Returns:
            True if window is open, False otherwise
        """
        window = self.get_window(task_id)
        if not window:
            return False

        return window.is_open()

    def extend_window(
        self, task_id: str, extension_seconds: int
    ) -> Optional[WindowInfo]:
        """
        Extend challenge window duration.

        Typically called when a valid challenge is submitted.

        Args:
            task_id: Task identifier
            extension_seconds: Additional time to add to window

        Returns:
            Updated WindowInfo or None if window doesn't exist
        """
        if extension_seconds <= 0:
            raise ValueError("Extension must be positive")

        with self.lock:
            # Get current window
            window = self.get_window(task_id)
            if not window:
                return None

            # Update duration and increment extended count
            new_duration = window.duration_seconds + extension_seconds
            new_extended_count = window.extended_count + 1

            with self.conn:
                self.conn.execute(
                    """
                    UPDATE challenge_windows
                    SET duration_seconds = ?, extended_count = ?
                    WHERE task_id = ?
                """,
                    (new_duration, new_extended_count, task_id),
                )

            print(
                f"[CHALLENGE_WINDOW] Extended window for task {task_id} by {extension_seconds}s "
                f"(total: {new_duration}s, extensions: {new_extended_count})"
            )

            return WindowInfo(
                task_id=task_id,
                opened_at_ns=window.opened_at_ns,
                duration_seconds=new_duration,
                extended_count=new_extended_count,
            )

    def close_window(self, task_id: str) -> bool:
        """
        Close a challenge window (delete from database).

        Args:
            task_id: Task identifier

        Returns:
            True if window was closed, False if it didn't exist
        """
        with self.lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    DELETE FROM challenge_windows WHERE task_id = ?
                """,
                    (task_id,),
                )

                return cursor.rowcount > 0

    def get_all_open_windows(self) -> list[WindowInfo]:
        """
        Get all currently open windows.

        Returns:
            List of WindowInfo objects for open windows
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT task_id, opened_at_ns, duration_seconds, extended_count
                FROM challenge_windows
            """
            )

            windows = []
            for row in cursor:
                window = WindowInfo(
                    task_id=row[0],
                    opened_at_ns=row[1],
                    duration_seconds=row[2],
                    extended_count=row[3],
                )
                if window.is_open():
                    windows.append(window)

            return windows
