"""
Tests for IPFS Migration Tool

Tests scanning, migration, mapping, and verification of FileCAS to IPFS migration.
"""

import pytest
import sys
import json
import tempfile
from pathlib import Path

# Add src and tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from migrate_to_ipfs import IPFSMigration
from cas_core import FileCAS, sha256_hash


@pytest.fixture
def temp_cas_dir(tmp_path):
    """Create a temporary FileCAS directory with test content"""
    cas_dir = tmp_path / ".cas"
    cas_dir.mkdir()

    # Create some test files
    test_files = {
        b"Hello World": None,
        b"Test content 1": None,
        b"Test content 2 with more data": None,
        b"{'key': 'value', 'data': [1,2,3]}": None,
    }

    # Store in FileCAS
    file_cas = FileCAS(cas_dir)
    for content in test_files.keys():
        file_hash = file_cas.put(content)
        test_files[content] = file_hash

    return cas_dir, test_files


@pytest.fixture
def migration_tool():
    """Create migration tool instance"""
    try:
        tool = IPFSMigration()
        yield tool
        tool.close()
    except ConnectionError:
        pytest.skip("IPFS daemon not running")


class TestFileCASScanning:
    """Tests for FileCAS directory scanning"""

    def test_scan_file_cas(self, temp_cas_dir, migration_tool):
        """Can scan FileCAS directory"""
        cas_dir, test_files = temp_cas_dir

        artifacts = migration_tool.scan_file_cas(cas_dir)

        # Should find all test files
        assert len(artifacts) == len(test_files)

        # Check that all hashes are found
        found_hashes = {hash for hash, path in artifacts}
        expected_hashes = set(test_files.values())
        assert found_hashes == expected_hashes

    def test_scan_empty_directory(self, tmp_path, migration_tool):
        """Empty directory returns empty list"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        artifacts = migration_tool.scan_file_cas(empty_dir)

        assert artifacts == []

    def test_scan_nonexistent_directory(self, tmp_path, migration_tool):
        """Nonexistent directory returns empty list"""
        nonexistent = tmp_path / "nonexistent"

        artifacts = migration_tool.scan_file_cas(nonexistent)

        assert artifacts == []


class TestMigration:
    """Tests for migration to IPFS"""

    def test_single_file_migration(self, migration_tool):
        """Can migrate a single file"""
        test_content = b"Single file migration test"
        test_hash = sha256_hash(test_content)

        # Create temporary CAS
        with tempfile.TemporaryDirectory() as tmpdir:
            cas_dir = Path(tmpdir) / ".cas"
            cas_dir.mkdir()

            # Store file
            file_cas = FileCAS(cas_dir)
            stored_hash = file_cas.put(test_content)
            assert stored_hash == test_hash

            # Migrate
            mappings = migration_tool.migrate_to_ipfs(cas_dir)

            # Should have one mapping
            assert len(mappings) == 1
            assert test_hash in mappings

            # Verify content in IPFS
            cid = mappings[test_hash]
            retrieved = migration_tool.ipfs_store.get(cid)
            assert retrieved == test_content

    def test_multiple_files_migration(self, temp_cas_dir, migration_tool):
        """Can migrate multiple files"""
        cas_dir, test_files = temp_cas_dir

        # Migrate all files
        mappings = migration_tool.migrate_to_ipfs(cas_dir)

        # Should have mapping for each file
        assert len(mappings) == len(test_files)

        # Verify all hashes are mapped
        for content, file_hash in test_files.items():
            assert file_hash in mappings

            # Verify content in IPFS
            cid = mappings[file_hash]
            retrieved = migration_tool.ipfs_store.get(cid)
            assert retrieved == content

    def test_hash_verification_during_migration(self, migration_tool):
        """Hash verification catches corrupted files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cas_dir = Path(tmpdir) / ".cas"
            cas_dir.mkdir()

            # Create a file with wrong hash
            wrong_hash = "a" * 64  # Invalid hash
            wrong_path = cas_dir / wrong_hash
            wrong_path.write_bytes(b"Corrupted content")

            # Migration should skip this file
            mappings = migration_tool.migrate_to_ipfs(cas_dir, verify_hash=True)

            # Should have no mappings (file skipped)
            assert len(mappings) == 0

    def test_migration_without_verification(self, migration_tool):
        """Can migrate without hash verification"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cas_dir = Path(tmpdir) / ".cas"
            cas_dir.mkdir()

            # Create a valid file
            content = b"Test content"
            file_hash = sha256_hash(content)
            (cas_dir / file_hash).write_bytes(content)

            # Migrate without verification
            mappings = migration_tool.migrate_to_ipfs(cas_dir, verify_hash=False)

            # Should succeed
            assert len(mappings) == 1
            assert file_hash in mappings


class TestMappingFile:
    """Tests for mapping file creation and loading"""

    def test_create_mapping_file(self, tmp_path, migration_tool):
        """Can create mapping file"""
        mappings = {"hash1": "QmCID1", "hash2": "QmCID2", "hash3": "QmCID3"}

        output_path = tmp_path / "mapping.json"

        migration_tool.create_mapping_file(mappings, output_path)

        # File should exist
        assert output_path.exists()

        # Load and verify
        with output_path.open() as f:
            data = json.load(f)

        assert data["version"] == "1.0"
        assert data["total_mappings"] == 3
        assert data["mappings"] == mappings
        assert "created_at" in data

    def test_load_mapping_file(self, tmp_path, migration_tool):
        """Can load mapping file"""
        mappings = {"hash1": "QmCID1", "hash2": "QmCID2"}

        output_path = tmp_path / "mapping.json"

        # Create
        migration_tool.create_mapping_file(mappings, output_path)

        # Load
        loaded_mappings = migration_tool.load_mapping_file(output_path)

        assert loaded_mappings == mappings

    def test_mapping_with_metadata(self, tmp_path, migration_tool):
        """Can include metadata in mapping file"""
        mappings = {"hash1": "QmCID1"}
        metadata = {"source": "/path/to/cas", "tool_version": "1.0"}

        output_path = tmp_path / "mapping.json"

        migration_tool.create_mapping_file(mappings, output_path, metadata)

        # Verify metadata
        with output_path.open() as f:
            data = json.load(f)

        assert data["metadata"] == metadata


class TestVerification:
    """Tests for migration verification"""

    def test_verify_successful_migration(self, temp_cas_dir, tmp_path, migration_tool):
        """Can verify successful migration"""
        cas_dir, test_files = temp_cas_dir

        # Migrate
        mappings = migration_tool.migrate_to_ipfs(cas_dir)

        # Create mapping file
        mapping_path = tmp_path / "mapping.json"
        migration_tool.create_mapping_file(mappings, mapping_path)

        # Verify
        verified, errors = migration_tool.verify_migration(mapping_path, cas_dir)

        assert verified == len(test_files)
        assert errors == 0

    def test_verify_without_original_cas(self, temp_cas_dir, tmp_path, migration_tool):
        """Can verify without original CAS directory"""
        cas_dir, test_files = temp_cas_dir

        # Migrate
        mappings = migration_tool.migrate_to_ipfs(cas_dir)

        # Create mapping file
        mapping_path = tmp_path / "mapping.json"
        migration_tool.create_mapping_file(mappings, mapping_path)

        # Verify without CAS dir (only checks IPFS)
        verified, errors = migration_tool.verify_migration(mapping_path)

        assert verified == len(test_files)
        assert errors == 0

    def test_verify_detects_missing_content(self, tmp_path, migration_tool):
        """Verification detects missing content in IPFS"""
        # Create fake mapping with non-existent CID
        mappings = {"hashA": "QmFakeCIDNotInIPFS123456789012345678901234"}

        mapping_path = tmp_path / "mapping.json"
        migration_tool.create_mapping_file(mappings, mapping_path)

        # Verify should fail
        verified, errors = migration_tool.verify_migration(mapping_path)

        assert verified == 0
        assert errors == 1


class TestEndToEnd:
    """End-to-end migration tests"""

    def test_complete_migration_workflow(self, temp_cas_dir, tmp_path, migration_tool):
        """Complete workflow: scan → migrate → map → verify"""
        cas_dir, test_files = temp_cas_dir

        # 1. Scan
        artifacts = migration_tool.scan_file_cas(cas_dir)
        assert len(artifacts) == len(test_files)

        # 2. Migrate
        mappings = migration_tool.migrate_to_ipfs(cas_dir)
        assert len(mappings) == len(test_files)

        # 3. Create mapping file
        mapping_path = tmp_path / "test_mapping.json"
        migration_tool.create_mapping_file(mappings, mapping_path)
        assert mapping_path.exists()

        # 4. Verify
        verified, errors = migration_tool.verify_migration(mapping_path, cas_dir)
        assert verified == len(test_files)
        assert errors == 0

        # 5. Verify content integrity
        for content, file_hash in test_files.items():
            cid = mappings[file_hash]
            retrieved = migration_tool.ipfs_store.get(cid)
            assert retrieved == content
            assert sha256_hash(retrieved) == file_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
