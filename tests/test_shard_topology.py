"""Tests for shard topology and cross-shard routing."""

import sys
import os
import pytest
from datetime import datetime
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sharding import ShardTopology, ShardRegistry, NodeInfo, CrossShardRouter


class TestShardTopology:
    """Test shard topology with consistent hashing."""

    def test_consistent_hashing(self):
        """Test that same need_id always maps to same shard."""
        topology = ShardTopology(num_shards=256)

        need_id = "thread-123-need-456"

        # Call multiple times, should always return same shard
        shard1 = topology.get_shard_for_need(need_id)
        shard2 = topology.get_shard_for_need(need_id)
        shard3 = topology.get_shard_for_need(need_id)

        assert shard1 == shard2 == shard3
        assert 0 <= shard1 < 256

    def test_distribution(self):
        """Test that needs are distributed across shards."""
        topology = ShardTopology(num_shards=256)

        # Generate 1000 need IDs and check distribution
        shard_counts = {}
        for i in range(1000):
            need_id = f"need-{i}"
            shard = topology.get_shard_for_need(need_id)
            shard_counts[shard] = shard_counts.get(shard, 0) + 1

        # Should use at least 50% of shards for reasonable distribution
        assert len(shard_counts) > 128

        # No single shard should have more than 2% of needs
        # (statistical test, may occasionally fail)
        for count in shard_counts.values():
            assert count < 20  # 2% of 1000

    def test_bucket_range(self):
        """Test bucket range calculation."""
        topology = ShardTopology(num_shards=256)

        # Check first shard
        min_hash, max_hash = topology.get_bucket_range(0)
        assert min_hash == 0
        assert max_hash > 0

        # Check last shard
        min_hash, max_hash = topology.get_bucket_range(255)
        assert min_hash > 0
        assert max_hash == (2**32 - 1)


class TestShardRegistry:
    """Test shard registry."""

    def test_register_shard(self):
        """Test node registration."""
        registry = ShardRegistry()

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["planner", "worker"],
        )

        nodes = registry.get_shard_nodes(0)
        assert len(nodes) == 1
        assert nodes[0].node_id == "node-1"
        assert nodes[0].address == "http://node1:8000"
        assert "planner" in nodes[0].capabilities

    def test_multiple_nodes_per_shard(self):
        """Test multiple nodes in same shard."""
        registry = ShardRegistry()

        # Register 3 nodes to shard 0
        for i in range(3):
            registry.register_shard(
                shard_id=0,
                node_id=f"node-{i}",
                address=f"http://node{i}:8000",
                capabilities=["worker"],
            )

        nodes = registry.get_shard_nodes(0)
        assert len(nodes) == 3

        node_ids = {n.node_id for n in nodes}
        assert node_ids == {"node-0", "node-1", "node-2"}

    def test_node_update(self):
        """Test updating existing node."""
        registry = ShardRegistry()

        # Initial registration
        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        # Update with new capabilities
        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker", "verifier"],
        )

        nodes = registry.get_shard_nodes(0)
        assert len(nodes) == 1
        assert "verifier" in nodes[0].capabilities

    def test_health_check(self):
        """Test shard health checking."""
        registry = ShardRegistry()

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        # Initially healthy
        assert registry.health_check(0) is True

        # Simulate old heartbeat (mock by setting timestamp to past)
        node = registry.nodes["node-1"]
        node.last_heartbeat_ns = 0  # Very old timestamp

        # Should be unhealthy now
        assert registry.health_check(0) is False

    def test_heartbeat_update(self):
        """Test heartbeat updates."""
        registry = ShardRegistry()

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        initial_heartbeat = registry.nodes["node-1"].last_heartbeat_ns

        # Small delay to ensure timestamp changes
        time.sleep(0.01)

        registry.update_heartbeat("node-1")

        updated_heartbeat = registry.nodes["node-1"].last_heartbeat_ns
        assert updated_heartbeat > initial_heartbeat

    def test_unregister_node(self):
        """Test node unregistration."""
        registry = ShardRegistry()

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        assert len(registry.get_shard_nodes(0)) == 1

        registry.unregister_node("node-1")

        assert len(registry.get_shard_nodes(0)) == 0
        assert "node-1" not in registry.nodes

    def test_shard_capabilities(self):
        """Test shard capability aggregation."""
        registry = ShardRegistry()

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["planner"],
        )

        registry.register_shard(
            shard_id=0,
            node_id="node-2",
            address="http://node2:8000",
            capabilities=["worker", "verifier"],
        )

        caps = registry.get_shard_capabilities(0)
        assert caps == {"planner", "worker", "verifier"}


class TestCrossShardRouter:
    """Test cross-shard routing."""

    def test_route_to_shard(self):
        """Test routing message to correct shard."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        # Register node in a shard
        registry.register_shard(
            shard_id=42,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        # Find a need_id that maps to shard 42
        need_id = None
        for i in range(10000):
            test_id = f"need-{i}"
            if topology.get_shard_for_need(test_id) == 42:
                need_id = test_id
                break

        assert need_id is not None, "Couldn't find need_id for shard 42"

        # Route to shard
        shard_id, endpoint = router.route_to_shard(need_id, {"test": "data"})

        assert shard_id == 42
        assert endpoint == "http://node1:8000"

    def test_no_healthy_endpoint(self):
        """Test routing fails when no healthy nodes."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        # Don't register any nodes

        with pytest.raises(ValueError, match="has no healthy nodes"):
            router.route_to_shard("need-123", {})

    def test_track_cross_shard_deps(self):
        """Test tracking cross-shard dependencies."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        need_id = "need-123"
        source_shard = topology.get_shard_for_need(need_id)

        # Track dependencies on other shards
        dep_shards = [(source_shard + 1) % 256, (source_shard + 2) % 256]
        router.track_cross_shard_deps(need_id, dep_shards)

        # Verify dependencies tracked
        deps = router.get_dependencies(need_id)
        assert len(deps) == 2

        to_shards = {d.to_shard for d in deps}
        assert to_shards == set(dep_shards)

    def test_same_shard_not_tracked(self):
        """Test same-shard dependencies are not tracked."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        need_id = "need-123"
        source_shard = topology.get_shard_for_need(need_id)

        # Try to track dependency on same shard
        router.track_cross_shard_deps(need_id, [source_shard])

        # Should not create any dependencies
        deps = router.get_dependencies(need_id)
        assert len(deps) == 0

    def test_add_dependency_artifact(self):
        """Test adding artifacts to dependencies."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        need_id = "need-123"
        source_shard = topology.get_shard_for_need(need_id)
        dep_shard = (source_shard + 1) % 256

        router.track_cross_shard_deps(need_id, [dep_shard])
        router.add_dependency_artifact(need_id, dep_shard, "hash-abc123")

        deps = router.get_dependencies(need_id)
        assert len(deps) == 1
        assert "hash-abc123" in deps[0].artifact_refs

    def test_clear_dependencies(self):
        """Test clearing dependencies after completion."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        need_id = "need-123"
        source_shard = topology.get_shard_for_need(need_id)

        router.track_cross_shard_deps(need_id, [(source_shard + 1) % 256])
        assert len(router.get_dependencies(need_id)) == 1

        router.clear_dependencies(need_id)
        assert len(router.get_dependencies(need_id)) == 0

    def test_get_shards_with_capability(self):
        """Test finding shards by capability."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        # Register nodes with different capabilities
        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["verifier"],
        )

        registry.register_shard(
            shard_id=1,
            node_id="node-2",
            address="http://node2:8000",
            capabilities=["worker"],
        )

        registry.register_shard(
            shard_id=2,
            node_id="node-3",
            address="http://node3:8000",
            capabilities=["verifier", "worker"],
        )

        # Find shards with verifier capability
        verifier_shards = router.get_shards_with_capability("verifier")
        assert set(verifier_shards) == {0, 2}

    def test_endpoint_caching(self):
        """Test endpoint cache works correctly."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        # First call should cache
        endpoint1 = router.get_shard_endpoint(0)
        assert endpoint1 == "http://node1:8000"
        assert 0 in router._endpoint_cache

        # Second call should use cache
        endpoint2 = router.get_shard_endpoint(0)
        assert endpoint2 == endpoint1

    def test_cache_invalidation(self):
        """Test cache invalidation when node becomes unhealthy."""
        topology = ShardTopology(num_shards=256)
        registry = ShardRegistry()
        router = CrossShardRouter(topology, registry)

        registry.register_shard(
            shard_id=0,
            node_id="node-1",
            address="http://node1:8000",
            capabilities=["worker"],
        )

        # Cache endpoint
        endpoint1 = router.get_shard_endpoint(0)
        assert 0 in router._endpoint_cache

        # Make node unhealthy
        registry.nodes["node-1"].last_heartbeat_ns = 0

        # Should return None and clear cache
        endpoint2 = router.get_shard_endpoint(0)
        assert endpoint2 is None
        assert 0 not in router._endpoint_cache
