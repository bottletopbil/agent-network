"""
Capability-Based Filtering

Filters agent manifests based on task requirements including I/O schema,
constraints, zone, and budget.
"""

from typing import List, Dict, Any, Optional
import logging

from .manifests import AgentManifest

logger = logging.getLogger(__name__)


class CapabilityFilter:
    """
    Filters agents by various criteria to find suitable candidates.

    Takes a large pool of agents and narrows it down based on:
    - I/O schema compatibility
    - Resource constraints
    - Geographic zone
    - Budget limits
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize capability filter.

        Args:
            strict_mode: If True, reject agents that don't perfectly match.
                        If False, use best-effort matching.
        """
        self.strict_mode = strict_mode

    def filter_by_io(
        self, need: Dict[str, Any], manifests: List[AgentManifest]
    ) -> List[AgentManifest]:
        """
        Filter agents by I/O schema compatibility.

        Checks if agent's input schema matches the task's output schema
        and if agent's output schema matches what the task needs.

        Args:
            need: Task NEED payload with input/output requirements
            manifests: List of agent manifests to filter

        Returns:
            List of compatible agents
        """
        required_input = need.get("input_schema", {})
        required_output = need.get("output_schema", {})

        if not required_input and not required_output:
            # No schema requirements
            return manifests

        compatible = []

        for manifest in manifests:
            io_schema = manifest.io_schema

            # Check input compatibility
            if required_input:
                agent_input = io_schema.get("input", {})
                if not self._schemas_compatible(required_input, agent_input):
                    logger.debug(f"Agent {manifest.agent_id} input schema incompatible")
                    continue

            # Check output compatibility
            if required_output:
                agent_output = io_schema.get("output", {})
                if not self._schemas_compatible(required_output, agent_output):
                    logger.debug(f"Agent {manifest.agent_id} output schema incompatible")
                    continue

            compatible.append(manifest)

        logger.info(f"I/O filtering: {len(manifests)} → {len(compatible)} agents")
        return compatible

    def filter_by_constraints(
        self, need: Dict[str, Any], manifests: List[AgentManifest]
    ) -> List[AgentManifest]:
        """
        Filter agents by resource constraints.

        Checks if agent meets minimum resource requirements like:
        - Memory (min_memory_gb)
        - CPU (min_cpu_cores)
        - GPU (requires_gpu)
        - Disk (min_disk_gb)

        Args:
            need: Task NEED payload with constraint requirements
            manifests: List of agent manifests to filter

        Returns:
            List of agents meeting constraints
        """
        required_constraints = need.get("constraints", {})

        if not required_constraints:
            return manifests

        compatible = []

        for manifest in manifests:
            agent_constraints = manifest.constraints

            # Check each required constraint
            meets_all = True
            for key, required_value in required_constraints.items():
                agent_value = agent_constraints.get(key)

                if agent_value is None:
                    if self.strict_mode:
                        meets_all = False
                        break
                    else:
                        # Assume agent can handle if not specified
                        continue

                # Numeric constraints (greater than or equal)
                if key.startswith("min_"):
                    if agent_value < required_value:
                        meets_all = False
                        break

                # Numeric constraints (less than or equal)
                elif key.startswith("max_"):
                    if agent_value > required_value:
                        meets_all = False
                        break

                # Boolean constraints (requires)
                elif key.startswith("requires_"):
                    if required_value and not agent_value:
                        meets_all = False
                        break

                # Exact match
                else:
                    if agent_value != required_value:
                        meets_all = False
                        break

            if meets_all:
                compatible.append(manifest)
            else:
                logger.debug(f"Agent {manifest.agent_id} doesn't meet constraints")

        logger.info(f"Constraint filtering: {len(manifests)} → {len(compatible)} agents")
        return compatible

    def filter_by_zone(
        self, need: Dict[str, Any], manifests: List[AgentManifest]
    ) -> List[AgentManifest]:
        """
        Filter agents by geographic/network zone.

        Prefers agents in the same zone as the requester for lower latency.
        Falls back to any zone if no agents in preferred zone.

        Args:
            need: Task NEED payload with zone preference
            manifests: List of agent manifests to filter

        Returns:
            List of agents in preferred zone (or all if none match)
        """
        preferred_zone = need.get("zone")

        if not preferred_zone:
            # No zone preference
            return manifests

        # Find agents in preferred zone
        in_zone = []
        out_of_zone = []

        for manifest in manifests:
            if manifest.zone == preferred_zone:
                in_zone.append(manifest)
            else:
                out_of_zone.append(manifest)

        if in_zone:
            logger.info(f"Zone filtering: {len(in_zone)} agents in zone '{preferred_zone}'")
            return in_zone
        else:
            logger.warning(f"No agents in preferred zone '{preferred_zone}', using all zones")
            return manifests

    def filter_by_budget(
        self, need: Dict[str, Any], manifests: List[AgentManifest]
    ) -> List[AgentManifest]:
        """
        Filter agents by budget constraints.

        Removes agents that are too expensive for the task budget.

        Args:
            need: Task NEED payload with budget limit
            manifests: List of agent manifests to filter

        Returns:
            List of agents within budget
        """
        max_price = need.get("max_price")

        if max_price is None:
            # No budget constraint
            return manifests

        within_budget = []

        for manifest in manifests:
            if manifest.price_per_task <= max_price:
                within_budget.append(manifest)
            else:
                logger.debug(
                    f"Agent {manifest.agent_id} too expensive: "
                    f"{manifest.price_per_task} > {max_price}"
                )

        logger.info(f"Budget filtering: {len(manifests)} → {len(within_budget)} agents")
        return within_budget

    def filter_all(
        self, need: Dict[str, Any], manifests: List[AgentManifest]
    ) -> List[AgentManifest]:
        """
        Apply all filters in sequence.

        Args:
            need: Task NEED payload with all requirements
            manifests: List of agent manifests to filter

        Returns:
            List of agents passing all filters
        """
        logger.info(f"Starting filter cascade with {len(manifests)} agents")

        # Filter by I/O schema
        candidates = self.filter_by_io(need, manifests)

        # Filter by constraints
        candidates = self.filter_by_constraints(need, candidates)

        # Filter by zone (prefers zone but doesn't eliminate)
        candidates = self.filter_by_zone(need, candidates)

        # Filter by budget
        candidates = self.filter_by_budget(need, candidates)

        logger.info(f"Filter cascade complete: {len(candidates)} agents qualified")
        return candidates

    def _schemas_compatible(self, required: Dict[str, Any], provided: Dict[str, Any]) -> bool:
        """
        Check if two schemas are compatible.

        This is a simplified check. In production, would use JSON Schema
        validation or similar.

        Args:
            required: Required schema
            provided: Provided schema

        Returns:
            True if compatible
        """
        if not required:
            return True

        if not provided and self.strict_mode:
            return False

        # Check type compatibility
        required_type = required.get("type")
        provided_type = provided.get("type")

        if required_type and provided_type:
            if required_type != provided_type:
                return False

        # Check required fields
        required_fields = set(required.get("required", []))
        provided_fields = set(provided.get("properties", {}).keys())

        if required_fields and not required_fields.issubset(provided_fields):
            if self.strict_mode:
                return False

        # In lenient mode, if types match or aren't specified, consider compatible
        return True


# Global filter instance
_global_filter: Optional[CapabilityFilter] = None


def get_filter(strict_mode: bool = False) -> CapabilityFilter:
    """Get or create the global capability filter"""
    global _global_filter
    if _global_filter is None or _global_filter.strict_mode != strict_mode:
        _global_filter = CapabilityFilter(strict_mode=strict_mode)
    return _global_filter
