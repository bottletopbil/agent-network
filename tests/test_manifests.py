"""Tests for agent manifests and registry."""

import sys
import os
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from identity import DIDManager, AgentManifest, ManifestManager, ManifestRegistry


class TestAgentManifest:
    """Test agent manifest creation and operations."""

    def test_create_manifest_dataclass(self):
        """Test creating manifest dataclass."""
        manifest = AgentManifest(
            agent_id="did:key:z123",
            capabilities=["planning", "execution"],
            io_schema={"input": "string", "output": "result"},
            price_per_task=1.5,
            avg_latency_ms=500,
            tags=["fast", "reliable"],
            pubkey="test_pubkey",
        )

        assert manifest.agent_id == "did:key:z123"
        assert len(manifest.capabilities) == 2
        assert manifest.price_per_task == 1.5

    def test_manifest_to_dict(self):
        """Test manifest serialization."""
        manifest = AgentManifest(
            agent_id="did:key:z123",
            capabilities=["test"],
            io_schema={},
            price_per_task=0.0,
            avg_latency_ms=100,
            tags=[],
            pubkey="pubkey",
        )

        manifest_dict = manifest.to_dict()

        assert isinstance(manifest_dict, dict)
        assert manifest_dict["agent_id"] == "did:key:z123"
        assert "capabilities" in manifest_dict

    def test_manifest_from_dict(self):
        """Test manifest deserialization."""
        data = {
            "agent_id": "did:key:z456",
            "capabilities": ["capability1"],
            "io_schema": {"test": "schema"},
            "price_per_task": 2.0,
            "avg_latency_ms": 200,
            "tags": ["tag1"],
            "pubkey": "key",
            "signature": "",
            "timestamp_ns": 0,
            "version": "1.0",
            "metadata": {},
        }

        manifest = AgentManifest.from_dict(data)

        assert manifest.agent_id == "did:key:z456"
        assert manifest.price_per_task == 2.0

    def test_compute_hash(self):
        """Test manifest hash computation."""
        manifest = AgentManifest(
            agent_id="did:key:z789",
            capabilities=["test"],
            io_schema={},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=["tag"],
            pubkey="key",
        )

        hash1 = manifest.compute_hash()

        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA256 hex

    def test_compute_hash_deterministic(self):
        """Test that same manifest produces same hash."""
        manifest1 = AgentManifest(
            agent_id="did:key:z001",
            capabilities=["cap1", "cap2"],
            io_schema={"in": "out"},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=["t1", "t2"],
            pubkey="key",
            timestamp_ns=12345,
        )

        manifest2 = AgentManifest(
            agent_id="did:key:z001",
            capabilities=["cap1", "cap2"],
            io_schema={"in": "out"},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=["t1", "t2"],
            pubkey="key",
            timestamp_ns=12345,
        )

        assert manifest1.compute_hash() == manifest2.compute_hash()

    def test_hash_ignores_signature(self):
        """Test that signature doesn't affect hash."""
        manifest = AgentManifest(
            agent_id="did:key:z002",
            capabilities=["test"],
            io_schema={},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=[],
            pubkey="key",
        )

        hash_before = manifest.compute_hash()
        manifest.signature = "some_signature"
        hash_after = manifest.compute_hash()

        assert hash_before == hash_after


class TestManifestManager:
    """Test manifest manager operations."""

    def test_create_manager(self):
        """Test creating manifest manager."""
        manager = ManifestManager()

        assert manager is not None
        assert manager.did_manager is not None

    def test_create_manifest(self):
        """Test creating manifest from agent info."""
        did_manager = DIDManager()
        manifest_mgr = ManifestManager(did_manager)

        # Create agent DID
        agent_did = did_manager.create_did_key()

        # Create manifest
        manifest = manifest_mgr.create_manifest(
            agent_id=agent_did,
            capabilities=["planning", "reasoning"],
            io_schema={"input": "task", "output": "plan"},
            price_per_task=2.5,
            avg_latency_ms=300,
            tags=["ai", "planner"],
        )

        assert manifest.agent_id == agent_did
        assert len(manifest.capabilities) == 2
        assert manifest.price_per_task == 2.5
        assert manifest.pubkey != ""

    def test_create_manifest_invalid_did(self):
        """Test creating manifest with invalid DID."""
        manifest_mgr = ManifestManager()

        with pytest.raises(ValueError):
            manifest_mgr.create_manifest(
                agent_id="did:invalid:000", capabilities=[], io_schema={}
            )

    def test_sign_manifest(self):
        """Test signing manifest."""
        did_manager = DIDManager()
        manifest_mgr = ManifestManager(did_manager)

        # Create agent and manifest
        agent_did = did_manager.create_did_key()
        manifest = manifest_mgr.create_manifest(
            agent_id=agent_did, capabilities=["test"], io_schema={}
        )

        # Sign manifest
        signed = manifest_mgr.sign_manifest(manifest)

        assert signed.signature != ""
        assert len(signed.signature) > 0

    def test_verify_manifest_valid(self):
        """Test verifying valid manifest."""
        did_manager = DIDManager()
        manifest_mgr = ManifestManager(did_manager)

        # Create and sign manifest
        agent_did = did_manager.create_did_key()
        manifest = manifest_mgr.create_manifest(
            agent_id=agent_did, capabilities=["test"], io_schema={}
        )
        signed = manifest_mgr.sign_manifest(manifest)

        # Verify
        is_valid = manifest_mgr.verify_manifest(signed)

        assert is_valid is True

    def test_verify_manifest_invalid(self):
        """Test verifying invalid manifest."""
        did_manager = DIDManager()
        manifest_mgr = ManifestManager(did_manager)

        agent_did = did_manager.create_did_key()
        manifest = manifest_mgr.create_manifest(
            agent_id=agent_did, capabilities=["test"], io_schema={}
        )

        # Sign with correct key
        signed = manifest_mgr.sign_manifest(manifest)

        # Tamper with manifest
        signed.price_per_task = 999.0

        # Verification should fail
        is_valid = manifest_mgr.verify_manifest(signed)

        assert is_valid is False

    def test_verify_unsigned_manifest(self):
        """Test verifying unsigned manifest."""
        manifest_mgr = ManifestManager()

        manifest = AgentManifest(
            agent_id="did:key:test",
            capabilities=[],
            io_schema={},
            price_per_task=0.0,
            avg_latency_ms=0,
            tags=[],
            pubkey="key",
            signature="",  # No signature
        )

        is_valid = manifest_mgr.verify_manifest(manifest)

        assert is_valid is False

    def test_publish_manifest(self):
        """Test publishing manifest to registry."""
        did_manager = DIDManager()
        manifest_mgr = ManifestManager(did_manager)
        registry = ManifestRegistry()

        # Create and sign manifest
        agent_did = did_manager.create_did_key()
        manifest = manifest_mgr.create_manifest(
            agent_id=agent_did, capabilities=["test"], io_schema={}
        )
        signed = manifest_mgr.sign_manifest(manifest)

        # Publish
        success = manifest_mgr.publish_manifest(signed, registry)

        assert success is True
        assert registry.count() == 1

    def test_publish_invalid_manifest(self):
        """Test publishing invalid manifest fails."""
        manifest_mgr = ManifestManager()
        registry = ManifestRegistry()

        manifest = AgentManifest(
            agent_id="did:key:test",
            capabilities=[],
            io_schema={},
            price_per_task=0.0,
            avg_latency_ms=0,
            tags=[],
            pubkey="key",
            signature="",
        )

        success = manifest_mgr.publish_manifest(manifest, registry)

        assert success is False
        assert registry.count() == 0


class TestManifestRegistry:
    """Test manifest registry operations."""

    def test_create_registry(self):
        """Test creating registry."""
        registry = ManifestRegistry()

        assert registry is not None
        assert registry.count() == 0

    def test_register_manifest(self):
        """Test registering manifest."""
        registry = ManifestRegistry()

        manifest = AgentManifest(
            agent_id="did:key:agent1",
            capabilities=["planning"],
            io_schema={},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=["fast"],
            pubkey="key",
        )

        success = registry.register(manifest)

        assert success is True
        assert registry.count() == 1

    def test_register_updates_existing(self):
        """Test that re-registering updates manifest."""
        registry = ManifestRegistry()

        manifest1 = AgentManifest(
            agent_id="did:key:agent1",
            capabilities=["cap1"],
            io_schema={},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=[],
            pubkey="key1",
        )

        manifest2 = AgentManifest(
            agent_id="did:key:agent1",
            capabilities=["cap2"],
            io_schema={},
            price_per_task=2.0,
            avg_latency_ms=200,
            tags=[],
            pubkey="key2",
        )

        registry.register(manifest1)
        registry.register(manifest2)

        # Should only have one manifest
        assert registry.count() == 1

        # Should be the updated one
        retrieved = registry.get_manifest("did:key:agent1")
        assert retrieved.price_per_task == 2.0

    def test_find_by_capability(self):
        """Test finding by capability."""
        registry = ManifestRegistry()

        # Register multiple agents
        for i in range(3):
            manifest = AgentManifest(
                agent_id=f"did:key:agent{i}",
                capabilities=["planning"] if i < 2 else ["execution"],
                io_schema={},
                price_per_task=1.0,
                avg_latency_ms=100,
                tags=[],
                pubkey=f"key{i}",
            )
            registry.register(manifest)

        # Find by capability
        planners = registry.find_by_capability("planning")

        assert len(planners) == 2

    def test_find_by_tag(self):
        """Test finding by tag."""
        registry = ManifestRegistry()

        for i in range(4):
            manifest = AgentManifest(
                agent_id=f"did:key:agent{i}",
                capabilities=[],
                io_schema={},
                price_per_task=1.0,
                avg_latency_ms=100,
                tags=["fast"] if i % 2 == 0 else ["slow"],
                pubkey=f"key{i}",
            )
            registry.register(manifest)

        fast_agents = registry.find_by_tag("fast")

        assert len(fast_agents) == 2

    def test_get_manifest(self):
        """Test getting specific manifest."""
        registry = ManifestRegistry()

        manifest = AgentManifest(
            agent_id="did:key:specific",
            capabilities=["test"],
            io_schema={},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=[],
            pubkey="key",
        )
        registry.register(manifest)

        retrieved = registry.get_manifest("did:key:specific")

        assert retrieved is not None
        assert retrieved.agent_id == "did:key:specific"

    def test_get_nonexistent_manifest(self):
        """Test getting nonexistent manifest."""
        registry = ManifestRegistry()

        manifest = registry.get_manifest("did:key:nonexistent")

        assert manifest is None

    def test_unregister(self):
        """Test unregistering agent."""
        registry = ManifestRegistry()

        manifest = AgentManifest(
            agent_id="did:key:remove",
            capabilities=["test"],
            io_schema={},
            price_per_task=1.0,
            avg_latency_ms=100,
            tags=["tag"],
            pubkey="key",
        )
        registry.register(manifest)

        # Unregister
        success = registry.unregister("did:key:remove")

        assert success is True
        assert registry.count() == 0
        assert registry.get_manifest("did:key:remove") is None

    def test_list_all(self):
        """Test listing all manifests."""
        registry = ManifestRegistry()

        for i in range(5):
            manifest = AgentManifest(
                agent_id=f"did:key:agent{i}",
                capabilities=[],
                io_schema={},
                price_per_task=1.0,
                avg_latency_ms=100,
                tags=[],
                pubkey=f"key{i}",
            )
            registry.register(manifest)

        all_manifests = registry.list_all()

        assert len(all_manifests) == 5

    def test_advanced_search(self):
        """Test advanced search with multiple criteria."""
        registry = ManifestRegistry()

        # Register diverse agents
        agents = [
            {
                "capabilities": ["planning"],
                "tags": ["fast"],
                "price": 1.0,
                "latency": 100,
            },
            {
                "capabilities": ["planning"],
                "tags": ["slow"],
                "price": 2.0,
                "latency": 500,
            },
            {
                "capabilities": ["execution"],
                "tags": ["fast"],
                "price": 0.5,
                "latency": 50,
            },
            {
                "capabilities": ["planning", "execution"],
                "tags": ["fast"],
                "price": 3.0,
                "latency": 1000,
            },
        ]

        for i, agent in enumerate(agents):
            manifest = AgentManifest(
                agent_id=f"did:key:agent{i}",
                capabilities=agent["capabilities"],
                io_schema={},
                price_per_task=agent["price"],
                avg_latency_ms=agent["latency"],
                tags=agent["tags"],
                pubkey=f"key{i}",
            )
            registry.register(manifest)

        # Search for fast planners under $2
        results = registry.search(
            capabilities=["planning"], tags=["fast"], max_price=2.0
        )

        assert len(results) == 1
        assert results[0].agent_id == "did:key:agent0"

    def test_get_capabilities(self):
        """Test getting all capabilities."""
        registry = ManifestRegistry()

        for i, caps in enumerate([["cap1"], ["cap2"], ["cap1", "cap3"]]):
            manifest = AgentManifest(
                agent_id=f"did:key:agent{i}",
                capabilities=caps,
                io_schema={},
                price_per_task=1.0,
                avg_latency_ms=100,
                tags=[],
                pubkey=f"key{i}",
            )
            registry.register(manifest)

        all_caps = registry.get_capabilities()

        assert "cap1" in all_caps
        assert "cap2" in all_caps
        assert "cap3" in all_caps

    def test_get_tags(self):
        """Test getting all tags."""
        registry = ManifestRegistry()

        for i, tags in enumerate([["tag1"], ["tag2"], ["tag1", "tag3"]]):
            manifest = AgentManifest(
                agent_id=f"did:key:agent{i}",
                capabilities=[],
                io_schema={},
                price_per_task=1.0,
                avg_latency_ms=100,
                tags=tags,
                pubkey=f"key{i}",
            )
            registry.register(manifest)

        all_tags = registry.get_tags()

        assert "tag1" in all_tags
        assert "tag2" in all_tags
        assert "tag3" in all_tags
