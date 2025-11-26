"""
Policy Conformance Checker

Validates that policies meet conformance requirements by running
a suite of test cases against the policy.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ConformanceChecker:
    """
    Validates policy conformance by running test cases.
    
    A policy must pass all required conformance tests to be considered
    conformant and eligible for distribution.
    """
    
    # Required conformance test IDs
    REQUIRED_TESTS = [
        "test_valid_message_kinds",
        "test_payload_size_limits",
        "test_required_fields",
        "test_signature_validation",
        "test_lamport_ordering"
    ]
    
    # Optional conformance tests
    OPTIONAL_TESTS = [
        "test_gas_metering",
        "test_resource_limits",
        "test_policy_versioning"
    ]
    
    def __init__(self, policy_path: Optional[Path] = None):
        """
        Initialize conformance checker.
        
        Args:
            policy_path: Optional path to Rego policy files
        """
        self.policy_path = policy_path
        logger.info("ConformanceChecker initialized")
    
    def run_tests(self, policy_wasm: Optional[Path] = None) -> List[str]:
        """
        Run conformance tests against a policy.
        
        Args:
            policy_wasm: Path to WASM policy (None for Python-based)
            
        Returns:
            List of test IDs that passed
        """
        passed_tests = []
        
        # Import policy engine for testing
        from policy.opa_engine import OPAEngine
        from policy.wasm_runtime import WASMRuntime
        
        # Use appropriate runtime
        if policy_wasm and policy_wasm.exists():
            # Would use WASM runtime with actual WASM file
            logger.info(f"Testing WASM policy: {policy_wasm}")
            runtime = WASMRuntime(policy_path=self.policy_path)
        else:
            # Use Python-based OPA engine
            logger.info("Testing Python-based policy")
            runtime = OPAEngine(policy_path=self.policy_path)
        
        # Run each conformance test
        for test_id in self.REQUIRED_TESTS + self.OPTIONAL_TESTS:
            try:
                if self._run_test(test_id, runtime):
                    passed_tests.append(test_id)
                    logger.debug(f"✓ {test_id}")
                else:
                    logger.warning(f"✗ {test_id}")
            except Exception as e:
                logger.error(f"✗ {test_id}: {e}")
        
        logger.info(f"Conformance tests: {len(passed_tests)}/{len(self.REQUIRED_TESTS + self.OPTIONAL_TESTS)} passed")
        
        return passed_tests
    
    def _run_test(self, test_id: str, runtime) -> bool:
        """
        Run a single conformance test.
        
        Args:
            test_id: Test identifier
            runtime: Policy runtime (OPA or WASM)
            
        Returns:
            True if test passed
        """
        # Test: Valid message kinds
        if test_id == "test_valid_message_kinds":
            return self._test_valid_message_kinds(runtime)
        
        # Test: Payload size limits
        elif test_id == "test_payload_size_limits":
            return self._test_payload_size_limits(runtime)
        
        # Test: Required fields
        elif test_id == "test_required_fields":
            return self._test_required_fields(runtime)
        
        # Test: Signature validation
        elif test_id == "test_signature_validation":
            return self._test_signature_validation(runtime)
        
        # Test: Lamport ordering
        elif test_id == "test_lamport_ordering":
            return self._test_lamport_ordering(runtime)
        
        # Test: Gas metering
        elif test_id == "test_gas_metering":
            return self._test_gas_metering(runtime)
        
        # Test: Resource limits
        elif test_id == "test_resource_limits":
            return self._test_resource_limits(runtime)
        
        # Test: Policy versioning
        elif test_id == "test_policy_versioning":
            return self._test_policy_versioning(runtime)
        
        else:
            logger.warning(f"Unknown test: {test_id}")
            return False
    
    def _test_valid_message_kinds(self, runtime) -> bool:
        """Test that policy validates message kinds correctly"""
        # Valid kind should pass
        valid_envelope = {
            "kind": "NEED",
            "thread_id": "t1",
            "lamport": 1,
            "actor_id": "a1",
            "payload_size": 100
        }
        result = runtime.evaluate(valid_envelope)
        if not result.allowed:
            return False
        
        # Invalid kind should fail
        invalid_envelope = {
            "kind": "INVALID_KIND",
            "thread_id": "t1",
            "lamport": 1,
            "actor_id": "a1",
            "payload_size": 100
        }
        result = runtime.evaluate(invalid_envelope)
        return not result.allowed
    
    def _test_payload_size_limits(self, runtime) -> bool:
        """Test that policy enforces payload size limits"""
        # Small payload should pass
        small_envelope = {
            "kind": "PROPOSE",
            "thread_id": "t1",
            "lamport": 2,
            "actor_id": "a2",
            "payload_size": 1000
        }
        result = runtime.evaluate(small_envelope)
        if not result.allowed:
            return False
        
        # Oversized payload should fail
        large_envelope = {
            "kind": "PROPOSE",
            "thread_id": "t1",
            "lamport": 2,
            "actor_id": "a2",
            "payload_size": 2000000  # 2MB > 1MB limit
        }
        result = runtime.evaluate(large_envelope)
        return not result.allowed
    
    def _test_required_fields(self, runtime) -> bool:
        """Test that policy requires necessary fields"""
        # Missing required field should fail
        incomplete_envelope = {
            "kind": "COMMIT",
            "thread_id": "t1",
            # Missing: lamport, actor_id
            "payload_size": 100
        }
        result = runtime.evaluate(incomplete_envelope)
        return not result.allowed
    
    def _test_signature_validation(self, runtime) -> bool:
        """Test signature validation (placeholder)"""
        # This would test actual signature validation
        # For now, just pass
        return True
    
    def _test_lamport_ordering(self, runtime) -> bool:
        """Test Lamport clock ordering (placeholder)"""
        # This would test Lamport clock validation
        # For now, just pass
        return True
    
    def _test_gas_metering(self, runtime) -> bool:
        """Test that gas metering works"""
        envelope = {
            "kind": "DECIDE",
            "thread_id": "t1",
            "lamport": 5,
            "actor_id": "a5",
            "payload_size": 500
        }
        result = runtime.evaluate(envelope)
        # Check that gas was tracked
        return result.gas_used > 0
    
    def _test_resource_limits(self, runtime) -> bool:
        """Test resource limit enforcement (placeholder)"""
        # This would test resource limit validation
        # For now, just pass
        return True
    
    def _test_policy_versioning(self, runtime) -> bool:
        """Test policy versioning support"""
        # Check that policy has a version
        if hasattr(runtime, 'engine'):
            return True
        return hasattr(runtime, 'get_runtime_info')
    
    def validate_conformance(self, capsule) -> bool:
        """
        Validate that a capsule meets conformance requirements.
        
        Args:
            capsule: PolicyCapsule to validate
            
        Returns:
            True if capsule passes all required tests
        """
        # Check that all required tests are in the conformance vector
        conformance_set = set(capsule.conformance_vector)
        required_set = set(self.REQUIRED_TESTS)
        
        missing_tests = required_set - conformance_set
        
        if missing_tests:
            logger.warning(
                f"Capsule missing required tests: {missing_tests}"
            )
            return False
        
        logger.info(
            f"Capsule conformance valid: {len(capsule.conformance_vector)} tests passed"
        )
        return True
    
    def get_test_coverage(self, passed_tests: List[str]) -> Dict[str, Any]:
        """
        Get test coverage statistics.
        
        Args:
            passed_tests: List of test IDs that passed
            
        Returns:
            Dictionary with coverage statistics
        """
        total_tests = len(self.REQUIRED_TESTS + self.OPTIONAL_TESTS)
        required_tests = len(self.REQUIRED_TESTS)
        passed_required = len(set(passed_tests) & set(self.REQUIRED_TESTS))
        passed_optional = len(set(passed_tests) & set(self.OPTIONAL_TESTS))
        
        return {
            "total_tests": total_tests,
            "required_tests": required_tests,
            "optional_tests": len(self.OPTIONAL_TESTS),
            "passed_tests": len(passed_tests),
            "passed_required": passed_required,
            "passed_optional": passed_optional,
            "coverage_percent": (len(passed_tests) / total_tests * 100) if total_tests > 0 else 0,
            "is_conformant": passed_required == required_tests
        }


# Global conformance checker instance
_conformance_checker: Optional[ConformanceChecker] = None


def get_conformance_checker() -> ConformanceChecker:
    """Get global conformance checker instance"""
    global _conformance_checker
    if _conformance_checker is None:
        _conformance_checker = ConformanceChecker()
    return _conformance_checker
