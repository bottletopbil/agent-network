"""Tests for DID (Decentralized Identifier) management."""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from identity import DIDManager


class TestDIDManager:
    """Test DID manager operations."""

    def test_create_manager(self):
        """Test creating DID manager."""
        manager = DIDManager()

        assert manager is not None
        assert len(manager.did_cache) == 0

    def test_create_did_key(self):
        """Test creating did:key identifier."""
        manager = DIDManager()

        did = manager.create_did_key()

        assert did.startswith("did:key:z")
        assert len(did) > 20

    def test_create_did_key_deterministic(self):
        """Test that same key produces same DID."""
        manager1 = DIDManager()
        manager2 = DIDManager()

        # Use same seed
        seed = b"a" * 32

        did1 = manager1.create_did_key(seed)
        did2 = manager2.create_did_key(seed)

        assert did1 == did2

    def test_create_did_peer(self):
        """Test creating did:peer identifier."""
        manager = DIDManager()

        peer_id = "12D3KooWExamplePeerID"
        did = manager.create_did_peer(peer_id)

        assert did.startswith("did:peer:0z")
        # Peer ID is base58 encoded, so it won't contain the original string

    def test_resolve_did_key(self):
        """Test resolving did:key to DID Document."""
        manager = DIDManager()

        # Create DID
        did = manager.create_did_key()

        # Resolve it
        doc = manager.resolve_did(did)

        assert doc is not None
        assert doc.id == did
        assert doc.public_key is not None
        assert len(doc.public_key) > 0

    def test_resolve_did_peer(self):
        """Test resolving did:peer to DID Document."""
        manager = DIDManager()

        # Create DID
        did = manager.create_did_peer("peer123")

        # Resolve it
        doc = manager.resolve_did(did)

        assert doc is not None
        assert doc.id == did

    def test_resolve_unknown_did(self):
        """Test resolving unknown DID method."""
        manager = DIDManager()

        doc = manager.resolve_did("did:unknown:abc123")

        assert doc is None

    def test_sign_with_did(self):
        """Test signing data with DID."""
        manager = DIDManager()

        # Create DID
        did = manager.create_did_key()

        # Sign some data
        data = b"Hello, DID world!"
        signature = manager.sign_with_did(data, did)

        assert signature is not None
        assert len(signature) == 64  # Ed25519 signature size

    def test_sign_with_unknown_did(self):
        """Test signing with unknown DID."""
        manager = DIDManager()

        data = b"test data"
        signature = manager.sign_with_did(data, "did:key:unknown")

        assert signature is None

    def test_verify_did_signature_valid(self):
        """Test verifying valid signature."""
        manager = DIDManager()

        # Create DID and sign data
        did = manager.create_did_key()
        data = b"Test message for verification"
        signature = manager.sign_with_did(data, did)

        # Verify signature
        is_valid = manager.verify_did_signature(data, signature, did)

        assert is_valid is True

    def test_verify_did_signature_invalid_data(self):
        """Test verifying signature with wrong data."""
        manager = DIDManager()

        # Create DID and sign data
        did = manager.create_did_key()
        data = b"Original message"
        signature = manager.sign_with_did(data, did)

        # Verify with different data
        wrong_data = b"Modified message"
        is_valid = manager.verify_did_signature(wrong_data, signature, did)

        assert is_valid is False

    def test_verify_did_signature_invalid_signature(self):
        """Test verifying invalid signature."""
        manager = DIDManager()

        did = manager.create_did_key()
        data = b"test data"

        # Use wrong signature
        wrong_signature = b"x" * 64
        is_valid = manager.verify_did_signature(data, wrong_signature, did)

        assert is_valid is False

    def test_export_import_did_key(self):
        """Test exporting and importing DID keys."""
        manager1 = DIDManager()
        manager2 = DIDManager()

        # Create DID in first manager
        did = manager1.create_did_key()

        # Export key
        private_key = manager1.export_did_key(did)
        assert private_key is not None
        assert len(private_key) == 32

        # Import into second manager
        success = manager2.import_did_key(did, private_key)
        assert success is True

        # Both should be able to sign the same way
        data = b"test message"
        sig1 = manager1.sign_with_did(data, did)
        sig2 = manager2.sign_with_did(data, did)

        assert sig1 == sig2

    def test_export_unknown_did(self):
        """Test exporting unknown DID."""
        manager = DIDManager()

        key = manager.export_did_key("did:key:unknown")
        assert key is None

    def test_did_document_to_dict(self):
        """Test DID document serialization."""
        manager = DIDManager()

        did = manager.create_did_key()
        doc = manager.resolve_did(did)

        doc_dict = doc.to_dict()

        assert "@context" in doc_dict
        assert doc_dict["id"] == did
        assert "verificationMethod" in doc_dict
        assert "authentication" in doc_dict


class TestDIDCaching:
    """Test DID caching behavior."""

    def test_did_cached_after_creation(self):
        """Test that DID is cached after creation."""
        manager = DIDManager()

        did = manager.create_did_key()

        assert did in manager.did_cache

    def test_did_cached_after_resolution(self):
        """Test that DID is cached after resolution."""
        manager = DIDManager()

        # Create DID
        did = manager.create_did_key()

        # Clear cache
        manager.did_cache.clear()

        # Resolve (should rebuild and cache)
        doc = manager.resolve_did(did)

        assert did in manager.did_cache
        assert manager.did_cache[did] == doc

    def test_resolve_uses_cache(self):
        """Test that resolve uses cached document."""
        manager = DIDManager()

        did = manager.create_did_key()

        # First resolution
        doc1 = manager.resolve_did(did)

        # Second resolution (should use cache)
        doc2 = manager.resolve_did(did)

        # Should be same object
        assert doc1 is doc2


class TestCrossDIDOperations:
    """Test operations across different DIDs."""

    def test_multiple_dids(self):
        """Test manager can handle multiple DIDs."""
        manager = DIDManager()

        # Create multiple DIDs
        did1 = manager.create_did_key()
        did2 = manager.create_did_key()
        did3 = manager.create_did_peer("peer123")

        assert did1 != did2
        assert did1 != did3
        assert len(manager.signing_keys) == 2  # peer DIDs don't have keys

    def test_sign_verify_different_dids(self):
        """Test that signature from one DID fails with another DID."""
        manager = DIDManager()

        # Create two different DIDs
        did1 = manager.create_did_key()
        did2 = manager.create_did_key()

        # Sign with first DID
        data = b"test message"
        signature = manager.sign_with_did(data, did1)

        # Verify with second DID (should fail)
        is_valid = manager.verify_did_signature(data, signature, did2)

        assert is_valid is False

    def test_cross_manager_verification(self):
        """Test signature verification across different manager instances."""
        manager1 = DIDManager()
        manager2 = DIDManager()

        # Create DID and sign in first manager
        did = manager1.create_did_key()
        data = b"cross-manager test"
        signature = manager1.sign_with_did(data, did)

        # Verify in second manager (should work, DID is self-contained)
        is_valid = manager2.verify_did_signature(data, signature, did)

        assert is_valid is True


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_sign_empty_data(self):
        """Test signing empty data."""
        manager = DIDManager()

        did = manager.create_did_key()
        signature = manager.sign_with_did(b"", did)

        assert signature is not None

        # Should verify
        is_valid = manager.verify_did_signature(b"", signature, did)
        assert is_valid is True

    def test_sign_large_data(self):
        """Test signing large data."""
        manager = DIDManager()

        did = manager.create_did_key()
        large_data = b"x" * 10000

        signature = manager.sign_with_did(large_data, did)

        assert signature is not None

        # Should verify
        is_valid = manager.verify_did_signature(large_data, signature, did)
        assert is_valid is True

    def test_resolve_malformed_did(self):
        """Test resolving malformed DID."""
        manager = DIDManager()

        # Not a valid did:key format
        doc = manager.resolve_did("did:key:invalidbase32")

        # Should fail gracefully
        assert doc is None

    def test_import_invalid_key(self):
        """Test importing invalid private key."""
        manager = DIDManager()

        # Wrong key length
        result = manager.import_did_key("did:key:test", b"short")

        assert result is False
