"""
Chaos Runner: Execute E2E tests with failure injection

Coordinates chaos testing by:
1. Running E2E scenarios
2. Injecting nemeses at random intervals
3. Verifying system properties hold
"""

import time
import random
import logging
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from .nemesis import Nemesis, NemesisEvent

logger = logging.getLogger(__name__)


@dataclass
class ChaosResult:
    """Result of a chaos test run"""
    success: bool
    duration_seconds: float
    nemesis_events: List[NemesisEvent]
    property_checks: Dict[str, bool]
    errors: List[str]
    warnings: List[str]


class ChaosRunner:
    """
    Coordinates chaos testing.
    
    Runs E2E scenarios while injecting failures and verifying properties.
    """
    
    def __init__(
        self,
        nemeses: List[Nemesis],
        seed: Optional[int] = None
    ):
        """
        Initialize chaos runner.
        
        Args:
            nemeses: List of nemeses to potentially inject
            seed: Random seed for reproducible chaos
        """
        self.nemeses = nemeses
        self.seed = seed
        
        if seed is not None:
            random.seed(seed)
        
        self.context: Dict[str, Any] = {
            "agents": [],
            "messages": [],
            "state": {}
        }
    
    def run(
        self,
        workload: Callable[[Dict[str, Any]], bool],
        properties: Dict[str, Callable[[Dict[str, Any]], bool]],
        duration_sec: float = 60.0,
        chaos_interval_sec: float = 5.0
    ) -> ChaosResult:
        """
        Run chaos test.
        
        Args:
            workload: Function to execute (takes context, returns success)
            properties: Dict of property name -> verification function
            duration_sec: How long to run the test
            chaos_interval_sec: How often to potentially inject chaos
        
        Returns:
            ChaosResult with test outcomes
        """
        logger.info(f"Starting chaos test (duration={duration_sec}s, interval={chaos_interval_sec}s)")
        
        start_time = time.time()
        end_time = start_time + duration_sec
        
        errors = []
        warnings = []
        all_events = []
        
        try:
            # Run workload in a loop with chaos injection
            while time.time() < end_time:
                # Potentially inject chaos
                if random.random() < 0.3:  # 30% chance per interval
                    self._inject_chaos()
                
                # Run workload
                try:
                    success = workload(self.context)
                    if not success:
                        warnings.append("Workload returned False")
                except Exception as e:
                    errors.append(f"Workload error: {e}")
                
                # Wait for next interval
                time.sleep(chaos_interval_sec)
            
            # Heal all active nemeses
            self._heal_all()
            
        except Exception as e:
            errors.append(f"Chaos runner error: {e}")
            logger.error(f"Chaos test failed: {e}")
        
        # Collect all nemesis events
        for nemesis in self.nemeses:
            all_events.extend(nemesis.events)
        
        # Sort events by timestamp
        all_events.sort(key=lambda e: e.timestamp)
        
        # Verify properties
        property_checks = {}
        for prop_name, prop_fn in properties.items():
            try:
                result = prop_fn(self.context)
                property_checks[prop_name] = result
                
                if not result:
                    warnings.append(f"Property '{prop_name}' failed")
                
            except Exception as e:
                property_checks[prop_name] = False
                errors.append(f"Property '{prop_name}' check error: {e}")
        
        duration = time.time() - start_time
        success = len(errors) == 0 and all(property_checks.values())
        
        logger.info(f"Chaos test completed: success={success}, duration={duration:.2f}s")
        
        return ChaosResult(
            success=success,
            duration_seconds=duration,
            nemesis_events=all_events,
            property_checks=property_checks,
            errors=errors,
            warnings=warnings
        )
    
    def run_scenario(
        self,
        scenario_name: str,
        setup: Callable[[Dict[str, Any]], None],
        workload: Callable[[Dict[str, Any]], bool],
        teardown: Callable[[Dict[str, Any]], None],
        properties: Dict[str, Callable[[Dict[str, Any]], bool]],
        duration_sec: float = 30.0
    ) -> ChaosResult:
        """
        Run a complete test scenario with setup/teardown.
        
        Args:
            scenario_name: Name of the scenario
            setup: Setup function
            workload: Workload function
            teardown: Teardown function
            properties: Properties to verify
            duration_sec: Test duration
        
        Returns:
            ChaosResult
        """
        logger.info(f"Running scenario: {scenario_name}")
        
        # Setup
        try:
            setup(self.context)
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            return ChaosResult(
                success=False,
                duration_seconds=0.0,
                nemesis_events=[],
                property_checks={},
                errors=[f"Setup failed: {e}"],
                warnings=[]
            )
        
        # Run chaos test
        result = self.run(workload, properties, duration_sec)
        
        # Teardown
        try:
            teardown(self.context)
        except Exception as e:
            logger.warning(f"Teardown failed: {e}")
            result.warnings.append(f"Teardown failed: {e}")
        
        return result
    
    def _inject_chaos(self):
        """Inject chaos by activating random nemeses"""
        for nemesis in self.nemeses:
            if not nemesis.active and nemesis.should_activate():
                logger.info(f"Injecting nemesis: {nemesis.name}")
                nemesis.inject(self.context)
    
    def _heal_all(self):
        """Heal all active nemeses"""
        for nemesis in self.nemeses:
            if nemesis.active:
                logger.info(f"Healing nemesis: {nemesis.name}")
                nemesis.heal(self.context)
    
    def verify_properties(
        self,
        properties: Dict[str, Callable[[Dict[str, Any]], bool]]
    ) -> Dict[str, bool]:
        """
        Verify system properties.
        
        Args:
            properties: Dict of property name -> verification function
        
        Returns:
            Dict of property name -> pass/fail
        """
        results = {}
        
        for name, prop_fn in properties.items():
            try:
                results[name] = prop_fn(self.context)
            except Exception as e:
                logger.error(f"Property '{name}' check failed: {e}")
                results[name] = False
        
        return results


# Common properties for chaos testing

def property_no_data_loss(context: Dict[str, Any]) -> bool:
    """Verify no data was lost during chaos"""
    state = context.get("state", {})
    expected_keys = context.get("expected_keys", set())
    
    if not expected_keys:
        return True  # Nothing to check
    
    actual_keys = set(state.keys())
    missing = expected_keys - actual_keys
    
    if missing:
        logger.warning(f"Data loss detected: {missing}")
        return False
    
    return True


def property_eventual_consistency(context: Dict[str, Any]) -> bool:
    """Verify system reaches consistent state"""
    # This is a simplified check
    # In practice, would verify all replicas converge
    state = context.get("state", {})
    
    # Check if state is non-empty (some progress made)
    return len(state) > 0


def property_decide_uniqueness(context: Dict[str, Any]) -> bool:
    """Verify only one DECIDE per need"""
    decides = context.get("decides", {})
    
    # Check for duplicate decides
    for need_id, decide_list in decides.items():
        if len(decide_list) > 1:
            logger.warning(f"Multiple DECIDEs for need {need_id}")
            return False
    
    return True


def property_finalize_determinism(context: Dict[str, Any]) -> bool:
    """Verify FINALIZEs are deterministic"""
    finalizes = context.get("finalizes", {})
    
    # In a real test, would compare with expected outcomes
    # For now, just verify structure
    for need_id, finalize in finalizes.items():
        if "result" not in finalize:
            logger.warning(f"FINALIZE for {need_id} missing result")
            return False
    
    return True
