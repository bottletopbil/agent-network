"""
Tests for Agent Registry.

Verifies registration, search, stats tracking, and API endpoints.
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from marketplace.registry import AgentRegistry, AgentStatus, SearchFilters, AgentStats


class TestAgentRegistration:
    """Test agent registration functionality"""
    
    @pytest.fixture
    def registry(self):
        """Create temporary registry for testing"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        reg = AgentRegistry(Path(db_file.name))
        
        yield reg
        
        # Cleanup
        os.unlink(db_file.name)
    
    def test_register_agent_basic(self, registry):
        """Test basic agent registration"""
        manifest = {
            "capabilities": ["code_analysis", "bug_detection"],
            "pricing": {"base_rate": 10.0},
            "tags": ["python"]
        }
        
        registration_id = registry.register_agent(
            agent_id="agent1",
            manifest=manifest,
            stake=100.0
        )
        
        assert registration_id is not None
        assert len(registration_id) > 0
    
    def test_register_duplicate_agent_fails(self, registry):
        """Test that registering duplicate agent fails"""
        manifest = {
            "capabilities": ["test"],
            "pricing": {"base_rate": 5.0}
        }
        
        # First registration succeeds
        registry.register_agent("agent1", manifest, 50.0)
        
        # Second registration should fail
        with pytest.raises(ValueError, match="already registered"):
            registry.register_agent("agent1", manifest, 50.0)
    
    def test_register_missing_capabilities_fails(self, registry):
        """Test that manifest without capabilities fails"""
        manifest = {"pricing": {"base_rate": 10.0}}  # Missing capabilities
        
        with pytest.raises(ValueError, match="capabilities"):
            registry.register_agent("agent1", manifest, 100.0)
    
    def test_register_missing_pricing_fails(self, registry):
        """Test that manifest without pricing fails"""
        manifest = {"capabilities": ["test"]}  # Missing pricing
        
        with pytest.raises(ValueError, match="pricing"):
            registry.register_agent("agent1", manifest, 100.0)


class TestManifestUpdates:
    """Test manifest update functionality"""
    
    @pytest.fixture
    def registry_with_agent(self):
        """Create registry with registered agent"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        reg = AgentRegistry(Path(db_file.name))
        
        # Register an agent
        manifest = {
            "capabilities": ["initial"],
            "pricing": {"base_rate": 10.0}
        }
        reg.register_agent("agent1", manifest, 100.0)
        
        yield reg
        
        os.unlink(db_file.name)
    
    def test_update_manifest(self, registry_with_agent):
        """Test updating agent manifest"""
        new_manifest = {
            "capabilities": ["updated", "new_capability"],
            "pricing": {"base_rate": 15.0},
            "tags": ["updated"]
        }
        
        result = registry_with_agent.update_manifest("agent1", new_manifest)
        assert result is True
    
    def test_update_nonexistent_agent_fails(self, registry_with_agent):
        """Test updating non-existent agent fails"""
        manifest = {"capabilities": ["test"], "pricing": {"base_rate": 10.0}}
        
        with pytest.raises(ValueError, match="not found"):
            registry_with_agent.update_manifest("nonexistent", manifest)


class TestAgentSearch:
    """Test agent search functionality"""
    
    @pytest.fixture
    def registry_with_agents(self):
        """Create registry with multiple agents"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        reg = AgentRegistry(Path(db_file.name))
        
        # Register multiple agents with different capabilities
        reg.register_agent(
            "agent1",
            {
                "capabilities": ["code_analysis", "python"],
                "pricing": {"base_rate": 10.0},
                "tags": ["backend"]
            },
            100.0
        )
        
        reg.register_agent(
            "agent2",
            {
                "capabilities": ["bug_detection", "security"],
                "pricing": {"base_rate": 15.0},
                "tags": ["security"]
            },
            150.0
        )
        
        reg.register_agent(
            "agent3",
            {
                "capabilities": ["code_analysis", "security"],
                "pricing": {"base_rate": 12.0},
                "tags": ["backend", "security"]
            },
            120.0
        )
        
        yield reg
        
        os.unlink(db_file.name)
    
    def test_search_all_agents(self, registry_with_agents):
        """Test searching without filters returns all agents"""
        results = registry_with_agents.search_agents()
        
        assert len(results) == 3
    
    def test_search_by_capability(self, registry_with_agents):
        """Test searching by specific capability"""
        results = registry_with_agents.search_agents(capabilities=["code_analysis"])
        
        assert len(results) == 2
        agent_ids = [r["agent_id"] for r in results]
        assert "agent1" in agent_ids
        assert "agent3" in agent_ids
    
    def test_search_by_multiple_capabilities(self, registry_with_agents):
        """Test searching by multiple capabilities (AND logic)"""
        results = registry_with_agents.search_agents(
            capabilities=["code_analysis", "security"]
        )
        
        assert len(results) == 1
        assert results[0]["agent_id"] == "agent3"
    
    def test_search_by_tags(self, registry_with_agents):
        """Test searching by tags"""
        filters = SearchFilters(tags=["security"])
        results = registry_with_agents.search_agents(filters=filters)
        
        assert len(results) == 2
        agent_ids = [r["agent_id"] for r in results]
        assert "agent2" in agent_ids
        assert "agent3" in agent_ids
    
    def test_search_by_status(self, registry_with_agents):
        """Test filtering by status"""
        # Set one agent to inactive
        registry_with_agents.set_agent_status("agent2", AgentStatus.INACTIVE)
        
        # Search for active only
        filters = SearchFilters(status=AgentStatus.ACTIVE)
        results = registry_with_agents.search_agents(filters=filters)
        
        assert len(results) == 2
        agent_ids = [r["agent_id"] for r in results]
        assert "agent1" in agent_ids
        assert "agent3" in agent_ids
        assert "agent2" not in agent_ids


class TestAgentStats:
    """Test agent statistics tracking"""
    
    @pytest.fixture
    def registry_with_agent(self):
        """Create registry with agent"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        reg = AgentRegistry(Path(db_file.name))
        
        manifest = {
            "capabilities": ["test"],
            "pricing": {"base_rate": 10.0}
        }
        reg.register_agent("agent1", manifest, 100.0)
        
        yield reg
        
        os.unlink(db_file.name)
    
    def test_get_initial_stats(self, registry_with_agent):
        """Test getting initial stats for new agent"""
        stats = registry_with_agent.get_agent_stats("agent1")
        
        assert stats is not None
        assert stats.agent_id == "agent1"
        assert stats.total_tasks == 0
        assert stats.completed_tasks == 0
        assert stats.failed_tasks == 0
        assert stats.success_rate == 0.0
        assert stats.reputation_score == 0.8  # Default
    
    def test_record_task_completion(self, registry_with_agent):
        """Test recording task completion"""
        # Record successful task
        registry_with_agent.record_task_completion(
            agent_id="agent1",
            success=True,
            response_time_ms=100.0,
            earnings=10.0
        )
        
        stats = registry_with_agent.get_agent_stats("agent1")
        
        assert stats.total_tasks == 1
        assert stats.completed_tasks == 1
        assert stats.failed_tasks == 0
        assert stats.success_rate == 1.0
        assert stats.avg_response_time_ms == 100.0
        assert stats.total_earnings == 10.0
    
    def test_record_task_failure(self, registry_with_agent):
        """Test recording task failure"""
        # Record failed task
        registry_with_agent.record_task_completion(
            agent_id="agent1",
            success=False,
            response_time_ms=50.0,
            earnings=0.0
        )
        
        stats = registry_with_agent.get_agent_stats("agent1")
        
        assert stats.total_tasks == 1
        assert stats.completed_tasks == 0
        assert stats.failed_tasks == 1
        assert stats.success_rate == 0.0
    
    def test_success_rate_calculation(self, registry_with_agent):
        """Test success rate calculation"""
        # Record mix of successes and failures
        registry_with_agent.record_task_completion("agent1", True, 100.0, 10.0)
        registry_with_agent.record_task_completion("agent1", True, 150.0, 15.0)
        registry_with_agent.record_task_completion("agent1", False, 50.0, 0.0)
        
        stats = registry_with_agent.get_agent_stats("agent1")
        
        assert stats.total_tasks == 3
        assert stats.completed_tasks == 2
        assert stats.failed_tasks == 1
        assert abs(stats.success_rate - 0.666666) < 0.001
    
    def test_update_reputation(self, registry_with_agent):
        """Test updating reputation score"""
        registry_with_agent.update_reputation("agent1", 0.95)
        
        stats = registry_with_agent.get_agent_stats("agent1")
        assert stats.reputation_score == 0.95
    
    def test_get_stats_nonexistent_agent(self, registry_with_agent):
        """Test getting stats for non-existent agent"""
        stats = registry_with_agent.get_agent_stats("nonexistent")
        assert stats is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
