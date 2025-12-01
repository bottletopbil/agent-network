"""
Derived Views for Plan State

Provides efficient materialized views and query interfaces on top
of the CRDT plan store.

Views:
- TaskView: Filter and query tasks by various criteria
- GraphView: Graph traversal and dependency analysis
"""

from typing import Dict, List, Set, Optional
from collections import defaultdict, deque


class TaskView:
    """
    Materialized view of tasks for efficient querying.

    Maintains indexes for common query patterns:
    - By state (DRAFT, DECIDED, VERIFIED, FINAL)
    - By thread
    - Ready tasks (no blockers)
    """

    def __init__(self, tasks: Dict):
        """
        Initialize task view.

        Args:
            tasks: Task dictionary from CRDT store
        """
        self.tasks = tasks
        self._build_indexes()

    def _build_indexes(self):
        """Build indexes for efficient querying"""
        # Index by state
        self.by_state: Dict[str, Set[str]] = defaultdict(set)

        # Index by thread
        self.by_thread: Dict[str, Set[str]] = defaultdict(set)

        for task_id, task in self.tasks.items():
            state = task.get("state", "DRAFT")
            thread_id = task.get("thread_id", "")

            self.by_state[state].add(task_id)
            self.by_thread[thread_id].add(task_id)

    def get_tasks_by_state(self, state: str) -> List[Dict]:
        """
        Get all tasks in a specific state.

        Args:
            state: Task state (DRAFT, DECIDED, VERIFIED, FINAL)

        Returns:
            List of task dictionaries
        """
        task_ids = self.by_state.get(state, set())
        return [self.tasks[tid] for tid in task_ids if tid in self.tasks]

    def get_tasks_by_thread(self, thread_id: str) -> List[Dict]:
        """
        Get all tasks in a specific thread.

        Args:
            thread_id: Thread identifier

        Returns:
            List of task dictionaries
        """
        task_ids = self.by_thread.get(thread_id, set())
        return [self.tasks[tid] for tid in task_ids if tid in self.tasks]

    def get_ready_tasks(self, graph_view: "GraphView") -> List[Dict]:
        """
        Get tasks that are ready to execute.

        A task is ready if:
        - State is DRAFT
        - Has no unfinished dependencies (blockers)

        Args:
            graph_view: GraphView for dependency checking

        Returns:
            List of ready task dictionaries
        """
        draft_tasks = self.get_tasks_by_state("DRAFT")
        ready = []

        for task in draft_tasks:
            task_id = task["task_id"]

            # Get parent dependencies
            parents = graph_view.get_parents(task_id)

            # Check if all parents are finished
            all_finished = True
            for parent_id in parents:
                parent = self.tasks.get(parent_id)
                if parent and parent.get("state") not in ["VERIFIED", "FINAL"]:
                    all_finished = False
                    break

            if all_finished:
                ready.append(task)

        return ready

    def get_all_tasks(self) -> List[Dict]:
        """Get all tasks"""
        return list(self.tasks.values())

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a specific task"""
        return self.tasks.get(task_id)

    def count_by_state(self) -> Dict[str, int]:
        """Get task counts by state"""
        return {state: len(task_ids) for state, task_ids in self.by_state.items()}


class GraphView:
    """
    Graph view for dependency analysis and traversal.

    Provides:
    - Parent/child relationships
    - Transitive closure (ancestors/descendants)
    - Topological sorting
    - Cycle detection
    """

    def __init__(self, edges: Dict[str, List[str]]):
        """
        Initialize graph view.

        Args:
            edges: Edge dictionary from CRDT store (parent -> [children])
        """
        self.edges = edges
        self._build_reverse_edges()

    def _build_reverse_edges(self):
        """Build reverse edge index (child -> [parents])"""
        self.reverse_edges: Dict[str, List[str]] = defaultdict(list)

        for parent, children in self.edges.items():
            for child in children:
                self.reverse_edges[child].append(parent)

    def get_children(self, task_id: str) -> List[str]:
        """
        Get direct children of a task.

        Args:
            task_id: Parent task ID

        Returns:
            List of child task IDs
        """
        return self.edges.get(task_id, [])

    def get_parents(self, task_id: str) -> List[str]:
        """
        Get direct parents of a task.

        Args:
            task_id: Child task ID

        Returns:
            List of parent task IDs
        """
        return self.reverse_edges.get(task_id, [])

    def get_ancestors(self, task_id: str) -> Set[str]:
        """
        Get all ancestors (transitive parents).

        Args:
            task_id: Task ID

        Returns:
            Set of ancestor task IDs
        """
        ancestors = set()
        visited = set()
        queue = deque([task_id])

        while queue:
            current = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            parents = self.get_parents(current)
            for parent in parents:
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.append(parent)

        return ancestors

    def get_descendants(self, task_id: str) -> Set[str]:
        """
        Get all descendants (transitive children).

        Args:
            task_id: Task ID

        Returns:
            Set of descendant task IDs
        """
        descendants = set()
        visited = set()
        queue = deque([task_id])

        while queue:
            current = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            children = self.get_children(current)
            for child in children:
                if child not in descendants:
                    descendants.add(child)
                    queue.append(child)

        return descendants

    def topological_sort(self, task_ids: Optional[Set[str]] = None) -> List[str]:
        """
        Perform topological sort on tasks.

        Returns tasks in dependency order (parents before children).
        Uses Kahn's algorithm.

        Args:
            task_ids: Optional subset of tasks to sort (defaults to all)

        Returns:
            List of task IDs in topological order

        Raises:
            ValueError: If graph contains cycles
        """
        if task_ids is None:
            # Get all nodes from both edges and reverse_edges
            task_ids = set(self.edges.keys()) | set(self.reverse_edges.keys())

        # Calculate in-degree for each task
        in_degree = defaultdict(int)
        for task_id in task_ids:
            in_degree[task_id] = 0

        for parent in task_ids:
            children = self.get_children(parent)
            for child in children:
                if child in task_ids:
                    in_degree[child] += 1

        # Start with tasks that have no dependencies
        queue = deque([tid for tid in task_ids if in_degree[tid] == 0])
        result = []

        while queue:
            current = queue.popleft()
            result.append(current)

            # Reduce in-degree for children
            for child in self.get_children(current):
                if child in task_ids:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        queue.append(child)

        # If not all tasks processed, there's a cycle
        if len(result) != len(task_ids):
            raise ValueError("Graph contains cycles - cannot perform topological sort")

        return result

    def detect_cycles(self) -> List[List[str]]:
        """
        Detect cycles in the dependency graph.

        Returns:
            List of cycles, where each cycle is a list of task IDs
        """
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(task_id: str, path: List[str]) -> bool:
            """DFS to detect cycles"""
            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task_id)

            for child in self.get_children(task_id):
                if child not in visited:
                    if dfs(child, path):
                        return True
                elif child in rec_stack:
                    # Found cycle - extract it from path
                    cycle_start = path.index(child)
                    cycle = path[cycle_start:] + [child]
                    cycles.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(task_id)
            return False

        # Check all nodes
        all_nodes = set(self.edges.keys()) | set(self.reverse_edges.keys())
        for task_id in all_nodes:
            if task_id not in visited:
                dfs(task_id, [])

        return cycles

    def is_reachable(self, from_task: str, to_task: str) -> bool:
        """
        Check if one task is reachable from another.

        Args:
            from_task: Start task ID
            to_task: Target task ID

        Returns:
            True if to_task is reachable from from_task
        """
        descendants = self.get_descendants(from_task)
        return to_task in descendants

    def get_leaf_tasks(self) -> List[str]:
        """
        Get all leaf tasks (tasks with no children).

        Returns:
            List of task IDs with no dependencies
        """
        all_nodes = set(self.edges.keys()) | set(self.reverse_edges.keys())
        return [
            task_id for task_id in all_nodes if len(self.get_children(task_id)) == 0
        ]

    def get_root_tasks(self) -> List[str]:
        """
        Get all root tasks (tasks with no parents).

        Returns:
            List of task IDs with no dependencies
        """
        all_nodes = set(self.edges.keys()) | set(self.reverse_edges.keys())
        return [task_id for task_id in all_nodes if len(self.get_parents(task_id)) == 0]
