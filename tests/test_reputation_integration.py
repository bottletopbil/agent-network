"""
Tests for Reputation Integration with DIDs.

Verifies that reputation is portable across agent instances via DIDs,
and that all systems (reputation tracking, manifests, scoring) integrate correctly.
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from economics.ledger import CreditLedger
from economics.stake import StakeManager
from economics.pools import VerifierPool, VerifierMetadata
from economics.reputation import ReputationTracker
from identity.did import DIDManager
from identity.manifest import ManifestManager, AgentManifest
from routing.scoring import AgentScorer


class TestDIDBasedReputation:
    """Test that reputation is tracked by DID"""

    def test_reputation_tracked_by_did(self):
        """Test that reputation events are tracked by DID"""
        # Setup
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        pool = VerifierPool(stake_manager)
        reputation_tracker = ReputationTracker(pool)

        # Create DID and register verifier
        did_manager = DIDManager()
        did = did_manager.create_did_key()

        ledger.create_account(did, 20000)
        stake_manager.stake(did, 10000)
        pool.register(
            did,
            10000,
            ["testing"],
            VerifierMetadata(
                org_id="org1", asn="AS1234", region="us-west", reputation=0.8
            ),
        )

        # Record attestation failure for DID
        reputation_tracker.record_attestation(did, "task_1", verdict=False)

        # Get reputation by DID
        reputation = reputation_tracker.get_reputation(did)

        # Should be reduced from 0.8 by failed attestation penalty (-0.3)
        assert reputation < 0.8
        assert reputation == pytest.approx(0.5, abs=0.01)

        # Get history by DID
        history = reputation_tracker.get_reputation_history(did)
        assert len(history) == 1
        assert history[0].did == did
        assert history[0].event_type == "ATTESTATION_FAILED"

        # Cleanup
        os.unlink(db_path)

    def test_reputation_portable_across_verifiers(self):
        """Test that reputation follows the DID, not the verifier instance"""
        # Setup
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        pool = VerifierPool(stake_manager)
        reputation_tracker = ReputationTracker(pool)

        # Create DID
        did_manager = DIDManager()
        did = did_manager.create_did_key()

        # Register first verifier instance with this DID
        ledger.create_account(did, 20000)
        stake_manager.stake(did, 10000)
        pool.register(
            did,
            10000,
            ["testing"],
            VerifierMetadata(
                org_id="org1", asn="AS1234", region="us-west", reputation=0.8
            ),
        )

        # Build reputation
        reputation_tracker.record_challenge(did, upheld=True)  # +0.1

        initial_reputation = reputation_tracker.get_reputation(did)
        assert initial_reputation == pytest.approx(0.9, abs=0.01)

        # Deregister and re-register (simulating new agent instance)
        pool.deregister(did)

        # Re-register with same DID
        stake_manager.stake(did, 5000)  # Stake more
        pool.register(
            did,
            15000,
            ["testing", "verification"],
            VerifierMetadata(
                org_id="org2",  # Different org
                asn="AS5678",  # Different ASN
                region="us-east",  # Different region
                reputation=0.8,  # Reset to default
            ),
        )

        # Update pool reputation to match tracker
        pool.update_reputation(did, initial_reputation)

        # Reputation should be preserved (tied to DID)
        current_reputation = reputation_tracker.get_reputation(did)
        assert current_reputation == pytest.approx(0.9, abs=0.01)

        # History should be preserved
        history = reputation_tracker.get_reputation_history(did)
        assert len(history) == 1
        assert history[0].did == did
        assert history[0].event_type == "CHALLENGE_SUCCESS"

        # Cleanup
        os.unlink(db_path)

    def test_reputation_in_manifest(self):
        """Test that manifests include DID-based reputation"""
        # Setup
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        pool = VerifierPool(stake_manager)
        reputation_tracker = ReputationTracker(pool)

        did_manager = DIDManager()
        did = did_manager.create_did_key()

        # Register verifier with DID
        ledger.create_account(did, 20000)
        stake_manager.stake(did, 10000)
        pool.register(
            did,
            10000,
            ["testing"],
            VerifierMetadata(
                org_id="org1", asn="AS1234", region="us-west", reputation=0.8
            ),
        )

        # Build some reputation
        reputation_tracker.record_challenge(did, upheld=True)  # +0.1
        reputation_tracker.record_challenge(did, upheld=True)  # +0.1

        expected_reputation = reputation_tracker.get_reputation(did)

        # Create manifest with reputation tracker
        manifest_manager = ManifestManager(
            did_manager=did_manager, reputation_tracker=reputation_tracker
        )

        manifest = manifest_manager.create_manifest(
            agent_id=did,
            capabilities=["code_review", "testing"],
            io_schema={"type": "object"},
            price_per_task=10.0,
            avg_latency_ms=500,
            tags=["python", "security"],
        )

        # Manifest should include DID-based reputation
        assert manifest.agent_id == did
        assert manifest.reputation == pytest.approx(expected_reputation, abs=0.01)
        assert manifest.reputation == pytest.approx(1.0, abs=0.01)  # 0.8 + 0.1 + 0.1

        # Cleanup
        os.unlink(db_path)

    def test_manifest_without_reputation_tracker(self):
        """Test that manifests use default reputation without tracker"""
        did_manager = DIDManager()
        did = did_manager.create_did_key()

        # Create manifest without reputation tracker
        manifest_manager = ManifestManager(did_manager=did_manager)

        manifest = manifest_manager.create_manifest(
            agent_id=did, capabilities=["code_review"], io_schema={"type": "object"}
        )

        # Should use default reputation (0.8)
        assert manifest.reputation == 0.8


class TestScoringIntegration:
    """Test that scoring system uses DID-based reputation"""

    def test_scoring_uses_manifest_reputation(self):
        """Test that scoring uses reputation from identity manifests"""
        did_manager = DIDManager()
        did = did_manager.create_did_key()

        # Create manifest with reputation
        manifest = AgentManifest(
            agent_id=did,
            capabilities=["testing"],
            io_schema={},
            price_per_task=10.0,
            avg_latency_ms=1000,
            tags=["python"],
            pubkey=did_manager.resolve_did(did).public_key,
            reputation=0.95,  # High reputation
        )

        # Score the manifest
        scorer = AgentScorer()
        need = {"capabilities": ["testing"], "max_price": 20.0, "max_latency_ms": 2000}

        scored = scorer.score_agent(manifest, need)

        # Reputation score should be 0.95
        assert scored.score_breakdown["reputation"] == 0.95
        assert scored.total_score > 0

    def test_scoring_fallback_to_success_rate(self):
        """Test that scoring falls back to success_rate for routing manifests"""
        from routing.manifests import AgentManifest as RoutingManifest

        # Create routing manifest with success_rate (no reputation field)
        manifest = RoutingManifest(
            agent_id="agent_123",
            capabilities=["testing"],
            io_schema={},
            success_rate=0.85,  # Routing manifests use success_rate
        )

        # Score the manifest
        scorer = AgentScorer()
        need = {"capabilities": ["testing"]}

        scored = scorer.score_agent(manifest, need)

        # Should use success_rate as reputation
        assert scored.score_breakdown["reputation"] == 0.85

    def test_end_to_end_reputation_flow(self):
        """Test complete flow: DID → reputation tracking → manifest → scoring"""
        # Setup
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        pool = VerifierPool(stake_manager)
        reputation_tracker = ReputationTracker(pool)
        did_manager = DIDManager()

        # Create DID and register verifier
        did = did_manager.create_did_key()
        ledger.create_account(did, 20000)
        stake_manager.stake(did, 10000)
        pool.register(
            did,
            10000,
            ["code_review"],
            VerifierMetadata(
                org_id="org1", asn="AS1234", region="us-west", reputation=0.8
            ),
        )

        # Build reputation through successful challenges
        reputation_tracker.record_challenge(did, upheld=True)  # +0.1
        reputation_tracker.record_challenge(did, upheld=True)  # +0.1

        # Create manifest with reputation tracker
        manifest_manager = ManifestManager(
            did_manager=did_manager, reputation_tracker=reputation_tracker
        )

        manifest = manifest_manager.create_manifest(
            agent_id=did,
            capabilities=["code_review", "security_audit"],
            io_schema={"type": "object"},
            price_per_task=5.0,
            avg_latency_ms=800,
            tags=["security", "python"],
        )

        # Score the manifest
        scorer = AgentScorer()
        need = {
            "capabilities": ["code_review"],
            "tags": ["security"],
            "max_price": 10.0,
            "max_latency_ms": 1000,
        }

        scored = scorer.score_agent(manifest, need)

        # Verify reputation flowed through entire system
        expected_reputation = 0.8 + 0.1 + 0.1  # Initial + 2 successful challenges
        assert manifest.reputation == pytest.approx(expected_reputation, abs=0.01)
        assert scored.score_breakdown["reputation"] == pytest.approx(
            expected_reputation, abs=0.01
        )
        assert scored.score_breakdown["reputation"] == 1.0  # Clamped to max

        # Cleanup
        os.unlink(db_path)


class TestBackwardCompatibility:
    """Test backward compatibility with verifier_id based code"""

    def test_reputation_events_have_both_did_and_verifier_id(self):
        """Test that reputation events store both DID and verifier_id"""
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        pool = VerifierPool(stake_manager)
        reputation_tracker = ReputationTracker(pool)

        did_manager = DIDManager()
        did = did_manager.create_did_key()

        ledger.create_account(did, 20000)
        stake_manager.stake(did, 10000)
        pool.register(
            did,
            10000,
            ["testing"],
            VerifierMetadata(
                org_id="org1", asn="AS1234", region="us-west", reputation=0.8
            ),
        )

        # Record event
        reputation_tracker.record_attestation(did, "task_1", verdict=True)

        # Query database directly to verify both columns exist
        cursor = pool.conn.execute(
            """
            SELECT did, verifier_id FROM reputation_events
        """
        )
        row = cursor.fetchone()

        # Both should be populated (currently with same value for compatibility)
        assert row is not None
        assert row[0] == did  # did column
        assert row[1] == did  # verifier_id column (same for now)

        # Cleanup
        os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
