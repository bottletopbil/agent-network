"""
Tests for IPFS-backed CAS Implementation

Tests CAS operations using IPFS as the backend storage.
"""

import pytest
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set IPFS_CAS environment variable for these tests
os.environ["IPFS_CAS"] = "true"

# Import CAS components
from cas import get_cas_store
from cas.ipfs_store import IPFSContentStore
from cas.feature_flag import use_ipfs_cas, set_cas_backend, reset_cas_backend


@pytest.fixture
def ipfs_store():
    """Create an IPFS content store for testing"""
    try:
        store = IPFSContentStore()
        yield store
        store.close()
    except ConnectionError:
        pytest.skip("IPFS daemon not running")


@pytest.fixture(autouse=True)
def ensure_ipfs_backend():
    """Ensure IPFS backend is selected for these tests"""
    set_cas_backend("ipfs")
    yield
    reset_cas_backend()


class TestIPFSContentStore:
    """Tests for IPFS content store operations"""

    def test_put_and_get(self, ipfs_store):
        """Can store and retrieve content"""
        test_data = b"Hello from IPFS CAS test!"

        # Store content
        cid = ipfs_store.put(test_data)

        assert cid is not None
        assert isinstance(cid, str)
        assert len(cid) > 0

        # Retrieve content
        retrieved = ipfs_store.get(cid)

        assert retrieved == test_data

    def test_cid_stability(self, ipfs_store):
        """Same data produces same CID"""
        test_data = b"Deterministic content"

        # Store same content twice
        cid1 = ipfs_store.put(test_data)
        cid2 = ipfs_store.put(test_data)

        # Should get same CID
        assert cid1 == cid2

        # Verify content
        retrieved1 = ipfs_store.get(cid1)
        retrieved2 = ipfs_store.get(cid2)

        assert retrieved1 == test_data
        assert retrieved2 == test_data
        assert retrieved1 == retrieved2

    def test_different_content_different_cid(self, ipfs_store):
        """Different data produces different CIDs"""
        data1 = b"Content A"
        data2 = b"Content B"

        cid1 = ipfs_store.put(data1)
        cid2 = ipfs_store.put(data2)

        assert cid1 != cid2

        # Verify each retrieves correct content
        assert ipfs_store.get(cid1) == data1
        assert ipfs_store.get(cid2) == data2

    def test_missing_content(self, ipfs_store):
        """Retrieving non-existent content raises KeyError"""
        fake_cid = "QmNotARealCIDForTesting123456789012345678901234"

        with pytest.raises(KeyError):
            ipfs_store.get(fake_cid)

    def test_exists(self, ipfs_store):
        """Can check if content exists"""
        test_data = b"Existence test"

        cid = ipfs_store.put(test_data)

        # Should exist
        assert ipfs_store.exists(cid) is True

        # Non-existent CID
        fake_cid = "QmNotARealCIDForTesting123456789012345678901234"
        assert ipfs_store.exists(fake_cid) is False

    def test_pinning(self, ipfs_store):
        """Can pin and unpin content"""
        test_data = b"Pinning test"

        # Add without auto-pin
        store_no_pin = IPFSContentStore(auto_pin=False)
        cid = store_no_pin.put(test_data)

        # Manually pin
        ipfs_store.pin(cid)

        # Check if pinned
        pins = ipfs_store.list_pins()
        assert cid in pins

        # Unpin
        ipfs_store.unpin(cid)

        # Note: Content may still exist in IPFS even after unpinning
        # It will be garbage collected eventually

        store_no_pin.close()

    def test_auto_pin(self, ipfs_store):
        """Auto-pinning works when enabled"""
        test_data = b"Auto-pin test"

        # Store with auto-pin (default)
        cid = ipfs_store.put(test_data)

        # Should be pinned
        pins = ipfs_store.list_pins()
        assert cid in pins

    def test_empty_bytes(self, ipfs_store):
        """Can store empty bytes"""
        empty_data = b""

        cid = ipfs_store.put(empty_data)

        assert cid is not None
        retrieved = ipfs_store.get(cid)
        assert retrieved == empty_data

    def test_large_content(self, ipfs_store):
        """Can handle larger content"""
        # 1MB of data
        large_data = b"x" * (1024 * 1024)

        cid = ipfs_store.put(large_data)
        retrieved = ipfs_store.get(cid)

        assert len(retrieved) == len(large_data)
        assert retrieved == large_data

    def test_type_validation(self, ipfs_store):
        """Put rejects non-bytes input"""
        with pytest.raises(TypeError):
            ipfs_store.put("not bytes")

        with pytest.raises(TypeError):
            ipfs_store.put(123)


class TestFeatureFlag:
    """Tests for CAS backend feature flag"""

    def test_use_ipfs_cas_env(self):
        """Feature flag reads from environment"""
        # Already set in fixture
        assert use_ipfs_cas() is True

    def test_programmatic_backend_selection(self):
        """Can programmatically set backend"""
        reset_cas_backend()

        set_cas_backend("ipfs")
        assert use_ipfs_cas() is True

        set_cas_backend("file")
        assert use_ipfs_cas() is False

        reset_cas_backend()

    def test_invalid_backend(self):
        """Invalid backend raises error"""
        with pytest.raises(ValueError):
            set_cas_backend("invalid")


class TestCASFactory:
    """Tests for CAS factory function"""

    def test_get_ipfs_store(self):
        """Factory returns IPFS store when flag is set"""
        set_cas_backend("ipfs")

        try:
            store = get_cas_store()
            assert isinstance(store, IPFSContentStore)
            store.close()
        except ConnectionError:
            pytest.skip("IPFS daemon not running")
        finally:
            reset_cas_backend()

    def test_ipfs_store_operations(self):
        """IPFS store works through factory"""
        set_cas_backend("ipfs")

        try:
            store = get_cas_store()

            # Test basic operations
            test_data = b"Factory test"
            cid = store.put(test_data)
            retrieved = store.get(cid)

            assert retrieved == test_data

            store.close()
        except ConnectionError:
            pytest.skip("IPFS daemon not running")
        finally:
            reset_cas_backend()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
