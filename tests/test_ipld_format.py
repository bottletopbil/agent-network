"""
Tests for IPLD Format and Merkle Proofs

Tests IPLD conversion, CID linking, and Merkle proof generation/verification
for envelopes and threads.
"""

import pytest
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cas.ipld_format import EnvelopeIPLD, ThreadIPLD, IPLDLink
from cas.merkle_proof import MerkleProof, hash_envelope
from cas import get_cas_store
from cas.feature_flag import set_cas_backend, reset_cas_backend


@pytest.fixture
def sample_envelope():
    """Create a sample envelope for testing"""
    return {
        "v": 1,
        "id": "test-envelope-123",
        "thread_id": "thread-456",
        "kind": "NEED",
        "lamport": 1,
        "ts_ns": 1234567890000,
        "sender_pk_b64": "senderkey123",
        "payload_hash": "abc123hash",
        "payload": {
            "task": "test task",
            "description": "test description",
            "data": [1, 2, 3]
        },
        "policy_engine_hash": "policy123",
        "nonce": "nonce123"
    }


@pytest.fixture
def ipfs_cas_store():
    """Create IPFS CAS store for testing"""
    try:
        set_cas_backend("ipfs")
        store = get_cas_store()
        yield store
        if hasattr(store, 'close'):
            store.close()
        reset_cas_backend()
    except ConnectionError:
        pytest.skip("IPFS daemon not running")


class TestEnvelopeIPLD:
    """Tests for envelope IPLD conversion"""
    
    def test_envelope_to_ipld_without_cas(self, sample_envelope):
        """Can convert envelope to IPLD format without CAS"""
        ipld = EnvelopeIPLD.to_ipld(sample_envelope)
        
        # Should have all basic fields
        assert ipld["id"] == "test-envelope-123"
        assert ipld["thread_id"] == "thread-456"
        assert ipld["kind"] == "NEED"
        assert ipld["lamport"] == 1
        
        # Payload should be inline (no CAS)
        assert "payload" in ipld
        assert isinstance(ipld["payload"], dict)
        assert ipld["payload"]["task"] == "test task"
    
    def test_envelope_to_ipld_with_cas(self, sample_envelope, ipfs_cas_store):
        """Can convert envelope with payload as CID link"""
        ipld = EnvelopeIPLD.to_ipld(sample_envelope, ipfs_cas_store)
        
        # Payload should be a CID link
        assert "payload" in ipld
        assert isinstance(ipld["payload"], dict)
        assert "/" in ipld["payload"]
        
        # Should be able to retrieve payload
        payload_cid = ipld["payload"]["/"]
        assert payload_cid is not None
    
    def test_ipld_round_trip(self, sample_envelope, ipfs_cas_store):
        """Can convert to IPLD and back"""
        # Convert to IPLD
        ipld = EnvelopeIPLD.to_ipld(sample_envelope, ipfs_cas_store)
        
        # Convert back
        reconstructed = EnvelopeIPLD.from_ipld(ipld, ipfs_cas_store)
        
        # Should match original (minus signature fields not in sample)
        assert reconstructed["id"] == sample_envelope["id"]
        assert reconstructed["thread_id"] == sample_envelope["thread_id"]
        assert reconstructed["kind"] == sample_envelope["kind"]
        assert reconstructed["lamport"] == sample_envelope["lamport"]
        assert reconstructed["payload"] == sample_envelope["payload"]
    
    def test_content_linking(self, sample_envelope, ipfs_cas_store):
        """Content linking creates valid CIDs"""
        ipld = EnvelopeIPLD.to_ipld(sample_envelope, ipfs_cas_store)
        
        # Check if payload is linked
        if EnvelopeIPLD.is_ipld_link(ipld["payload"]):
            payload_cid = EnvelopeIPLD.get_cid_from_link(ipld["payload"])
            
            assert payload_cid is not None
            assert len(payload_cid) > 0
            
            # Should be able to retrieve from CAS
            retrieved = ipfs_cas_store.get(payload_cid)
            assert retrieved is not None
            
            # Should match original payload
            payload_data = json.loads(retrieved.decode('utf-8'))
            assert payload_data == sample_envelope["payload"]
    
    def test_is_ipld_link(self):
        """Can identify IPLD links"""
        # Valid link
        link = {"/": "QmCID123"}
        assert EnvelopeIPLD.is_ipld_link(link) is True
        
        # Not a link
        assert EnvelopeIPLD.is_ipld_link({"data": "value"}) is False
        assert EnvelopeIPLD.is_ipld_link("string") is False
        assert EnvelopeIPLD.is_ipld_link(123) is False
    
    def test_get_cid_from_link(self):
        """Can extract CID from link"""
        link = {"/": "QmTestCID123"}
        cid = EnvelopeIPLD.get_cid_from_link(link)
        
        assert cid == "QmTestCID123"
        
        # Non-link returns None
        assert EnvelopeIPLD.get_cid_from_link({"data": "value"}) is None


class TestThreadIPLD:
    """Tests for thread IPLD DAG"""
    
    def test_envelopes_to_dag(self, ipfs_cas_store):
        """Can convert envelopes to thread DAG"""
        envelopes = [
            {"id": "env1", "kind": "NEED", "payload": {"task": "1"}},
            {"id": "env2", "kind": "PROPOSE", "payload": {"task": "2"}},
            {"id": "env3", "kind": "DECIDE", "payload": {"task": "3"}}
        ]
        
        thread = ThreadIPLD(ipfs_cas_store)
        dag = thread.envelopes_to_dag(envelopes, "thread-123")
        
        assert dag["thread_id"] == "thread-123"
        assert dag["envelope_count"] == 3
        assert len(dag["envelopes"]) == 3
        assert dag["version"] == "1.0"
    
    def test_dag_round_trip(self, ipfs_cas_store):
        """Can convert DAG back to envelopes"""
        original_envelopes = [
            {"id": "env1", "kind": "NEED", "lamport": 1, "payload": {"task": "1"}},
            {"id": "env2", "kind": "PROPOSE", "lamport": 2, "payload": {"task": "2"}}
        ]
        
        thread = ThreadIPLD(ipfs_cas_store)
        
        # Convert to DAG
        dag = thread.envelopes_to_dag(original_envelopes, "thread-123")
        
        # Convert back
        reconstructed = thread.dag_to_envelopes(dag)
        
        assert len(reconstructed) == len(original_envelopes)
        
        for original, reconstructed_env in zip(original_envelopes, reconstructed):
            assert reconstructed_env["id"] == original["id"]
            assert reconstructed_env["kind"] == original["kind"]
            assert reconstructed_env["payload"] == original["payload"]
    
    def test_store_and_load_thread_dag(self, ipfs_cas_store):
        """Can store and load thread DAG"""
        envelopes = [
            {"id": "env1", "kind": "NEED", "payload": {"task": "1"}},
            {"id": "env2", "kind": "PROPOSE", "payload": {"task": "2"}}
        ]
        
        thread = ThreadIPLD(ipfs_cas_store)
        
        # Create DAG
        dag = thread.envelopes_to_dag(envelopes, "thread-123")
        
        # Store DAG
        root_cid = thread.store_thread_dag(dag)
        assert root_cid is not None
        
        # Load DAG
        loaded_dag = thread.load_thread_dag(root_cid)
        
        assert loaded_dag["thread_id"] == "thread-123"
        assert loaded_dag["envelope_count"] == 2


class TestMerkleProof:
    """Tests for Merkle proof generation and verification"""
    
    def test_build_tree(self):
        """Can build Merkle tree"""
        leaves = ["hash1", "hash2", "hash3", "hash4"]
        
        tree = MerkleProof.build_tree(leaves)
        
        # Should have multiple levels
        assert len(tree) > 1
        
        # First level should be leaves
        assert tree[0] == leaves
        
        # Last level should be root (single node)
        assert len(tree[-1]) == 1
    
    def test_get_root(self):
        """Can get root from tree"""
        leaves = ["hash1", "hash2", "hash3"]
        tree = MerkleProof.build_tree(leaves)
        
        root = MerkleProof.get_root(tree)
        
        assert root is not None
        assert isinstance(root, str)
    
    def test_merkle_proof_generation(self):
        """Can generate Merkle proof"""
        envelopes = [
            {"id": "env1", "data": "1"},
            {"id": "env2", "data": "2"},
            {"id": "env3", "data": "3"},
            {"id": "env4", "data": "4"}
        ]
        
        # Generate proof for index 2
        proof = MerkleProof.build_proof(envelopes, 2)
        
        assert proof["target_index"] == 2
        assert proof["target_hash"] == hash_envelope(envelopes[2])
        assert "root" in proof
        assert "siblings" in proof
        assert "path" in proof
        assert proof["tree_size"] == 4
    
    def test_merkle_proof_verification(self):
        """Can verify Merkle proof"""
        envelopes = [
            {"id": "env1", "data": "1"},
            {"id": "env2", "data": "2"},
            {"id": "env3", "data": "3"},
            {"id": "env4", "data": "4"}
        ]
        
        # Generate proof
        proof = MerkleProof.build_proof(envelopes, 2)
        root = proof["root"]
        
        # Verify proof
        is_valid = MerkleProof.verify_proof(root, envelopes[2], proof)
        
        assert is_valid is True
    
    def test_proof_verification_fails_for_wrong_envelope(self):
        """Proof verification fails for wrong envelope"""
        envelopes = [
            {"id": "env1", "data": "1"},
            {"id": "env2", "data": "2"},
            {"id": "env3", "data": "3"},
            {"id": "env4", "data": "4"}
        ]
        
        # Generate proof for index 2
        proof = MerkleProof.build_proof(envelopes, 2)
        root = proof["root"]
        
        # Try to verify with wrong envelope (index 1)
        is_valid = MerkleProof.verify_proof(root, envelopes[1], proof)
        
        assert is_valid is False
    
    def test_compute_root_from_envelopes(self):
        """Can compute Merkle root directly"""
        envelopes = [
            {"id": "env1"},
            {"id": "env2"},
            {"id": "env3"}
        ]
        
        root = MerkleProof.compute_root_from_envelopes(envelopes)
        
        assert root is not None
        assert isinstance(root, str)
        assert len(root) == 64  # SHA256
    
    def test_verify_envelope_in_thread(self):
        """Can verify envelope at position in thread"""
        envelopes = [
            {"id": "env1", "lamport": 1},
            {"id": "env2", "lamport": 2},
            {"id": "env3", "lamport": 3}
        ]
        
        # Verify envelope at index 1
        is_valid, proof = MerkleProof.verify_envelope_in_thread(
            envelopes[1],
            envelopes,
            1
        )
        
        assert is_valid is True
        assert proof is not None
        assert proof["target_index"] == 1


class TestIPLDLink:
    """Tests for IPLD link dataclass"""
    
    def test_to_dict(self):
        """Can convert to IPLD link format"""
        link = IPLDLink(cid="QmTestCID123")
        link_dict = link.to_dict()
        
        assert link_dict == {"/": "QmTestCID123"}
    
    def test_from_dict(self):
        """Can create from IPLD link format"""
        link_dict = {"/": "QmTestCID456"}
        link = IPLDLink.from_dict(link_dict)
        
        assert link.cid == "QmTestCID456"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
