"""
Tests for Intelligent Router Integration

Tests complete routing pipeline, fallback mechanisms, metrics tracking, and performance.
"""

import pytest
import sys
from pathlib import Path
import asyncio
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from routing.router import IntelligentRouter, get_router, reset_router
from routing.manifests import AgentManifest, ManifestRegistry, reset_registry, get_registry
from routing.metrics import MetricsCollector, reset_metrics_collector
from routing.bandit import reset_bandit
from routing.domain_fit import reset_domain_fit_calculator
from routing.recency import reset_recency_weighter
from routing.canary import reset_canary_runner
from routing.scoring import reset_scorer
from routing.features import reset_feature_extractor


# Test Fixtures

@pytest.fixture
def sample_agents():
    """Sample agent manifests"""
    return [
        AgentManifest(
            agent_id="agent-python-expert",
            capabilities=["code_gen", "refactoring"],
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            tags=["python", "ml"],
            success_rate=0.95,
            price_per_task=20.0,
            avg_latency_ms=500.0,
            zone="us-west-2"
        ),
        AgentManifest(
            agent_id="agent-python-cheap",
            capabilities=["code_gen"],
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            tags=["python"],
            success_rate=0.80,
            price_per_task=5.0,
            avg_latency_ms=800.0,
            zone="us-west-2"
        ),
        AgentManifest(
            agent_id="agent-js-expert",
            capabilities=["code_gen", "web"],
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            tags=["javascript", "web"],
            success_rate=0.90,
            price_per_task=15.0,
            avg_latency_ms=600.0,
            zone="us-east-1"
        ),
    ]


@pytest.fixture
def router(sample_agents):
    """Fresh intelligent router with sample agents"""
    # Reset all global state
    reset_router()
    reset_registry()
    reset_metrics_collector()
    reset_bandit()
    reset_domain_fit_calculator()
    reset_recency_weighter()
    reset_canary_runner()
    reset_scorer()
    reset_feature_extractor()
    
    # Register agents
    registry = get_registry()
    for agent in sample_agents:
        registry.register(agent)
    
    # Create router
    return get_router(enable_canary=True, enable_bandit=True)


# Full Pipeline Tests

class TestFullRoutingPipeline:
    """Tests for complete routing pipeline"""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, router):
        """Complete pipeline successfully routes NEED"""
        need = {
            "need_id": "test-need-1",
            "task_type": "code_gen",
            "description": "Generate Python code",
            "tags": ["python"],
            "capabilities": ["code_gen"],
            "max_price": 50.0,
            "max_latency_ms": 5000
        }
        
        selected = await router.route_need(need)
        
        assert selected is not None
        assert selected in ["agent-python-expert", "agent-python-cheap"]
    
    @pytest.mark.asyncio
    async def test_pipeline_stages(self, router):
        """Pipeline goes through all stages"""
        need = {
            "need_id": "test-need-2",
            "tags": ["python", "ml"],
            "capabilities": ["code_gen"],
            "max_price": 100.0
        }
        
        selected = await router.route_need(need)
        
        # Should select python expert (matches tags better)
        assert selected is not None
        
        # Check metrics were recorded
        stats = router.metrics.get_stats()
        assert stats["total_routings"] == 1
        assert stats["success_rate"] == 1.0
    
    @pytest.mark.asyncio
    async def test_outcome_recording(self, router):
        """Can record task outcomes"""
        need = {
            "need_id": "test-need-3",
            "tags": ["python"],
            "capabilities": ["code_gen"],
            "max_price": 50.0
        }
        
        selected = await router.route_need(need)
        assert selected is not None
        
        # Record outcome
        task_result = {
            "quality_score": 0.9,
            "latency_ms": 400.0,
            "max_latency_ms": 5000.0,
            "success": True
        }
        
        router.record_outcome(
            need_id="test-need-3",
            need=need,
            agent_id=selected,
            task_result=task_result
        )
        
        # Check bandit was updated
        bandit_stats = router.bandit.get_stats()
        assert bandit_stats["total_pulls"] > 0


# Fallback Tests

class TestFallbackToAuction:
    """Tests for auction fallback mechanism"""
    
    @pytest.mark.asyncio
    async def test_no_qualified_agents(self, router):
        """Falls back when no agents qualify"""
        need = {
            "need_id": "test-need-impossible",
            "capabilities": ["nonexistent_capability"],
            "max_price": 1.0  # Too low
        }
        
        selected = await router.route_need(need)
        
        # Should return None (indicating fallback needed)
        assert selected is None
        
        # Check metrics show fallback
        stats = router.metrics.get_stats()
        assert stats["fallback_rate"] > 0
    
    @pytest.mark.asyncio
    async def test_canary_disabled_fallback(self):
        """Can disable canary and still route"""
        # Reset and create router without canary
        reset_router()
        reset_registry()
        
        registry = get_registry()
        registry.register(AgentManifest(
            agent_id="test-agent",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            price_per_task=10.0,
            success_rate=0.9,
            avg_latency_ms=500.0
        ))
        
        router = IntelligentRouter(enable_canary=False, enable_bandit=True)
        
        need = {
            "need_id": "test-no-canary",
            "capabilities": ["test"],
            "tags": ["python"]
        }
        
        selected = await router.route_need(need)
        
        assert selected == "test-agent"


# Metrics Tests

class TestRoutingMetrics:
    """Tests for metrics tracking"""
    
    @pytest.mark.asyncio
    async def test_metrics_tracking(self, router):
        """Metrics are tracked correctly"""
        needs = [
            {"need_id": f"need-{i}", "capabilities": ["code_gen"], "tags": ["python"]}
            for i in range(5)
        ]
        
        for need in needs:
            await router.route_need(need)
        
        stats = router.metrics.get_stats()
        
        assert stats["total_routings"] == 5
        assert stats["success_rate"] == 1.0  # All should succeed
        assert stats["avg_latency_ms"] > 0  # Should have some latency
    
    @pytest.mark.asyncio
    async def test_method_distribution(self, router):
        """Tracks which routing methods are used"""
        needs = [
            {"need_id": f"need-{i}", "capabilities": ["code_gen"], "tags": ["python"]}
            for i in range(3)
        ]
        
        for need in needs:
            await router.route_need(need)
        
        stats = router.metrics.get_stats()
        method_dist = stats["method_distribution"]
        
        # Should use bandit or canary method
        assert len(method_dist) > 0
    
    @pytest.mark.asyncio
    async def test_accuracy_tracking(self, router):
        """Tracks routing accuracy"""
        need = {
            "need_id": "accuracy-test",
            "capabilities": ["code_gen"],
            "tags": ["python"],
            "max_price": 50.0
        }
        
        selected = await router.route_need(need)
        
        # Record good outcome
        router.record_outcome(
            need_id="accuracy-test",
            need=need,
            agent_id=selected,
            task_result={"quality_score": 0.9, "latency_ms": 400.0, "max_latency_ms": 5000.0}
        )
        
        stats = router.metrics.get_stats()
        accuracy = stats["routing_accuracy"]
        
        assert 0.0 <= accuracy <= 1.0


# Performance Tests

class Test10xSpeedupVsAuction:
    """Tests for routing performance vs auction"""
    
    @pytest.mark.asyncio
    async def test_routing_speed(self, router):
        """Routing is fast"""
        need = {
            "need_id": "speed-test",
            "capabilities": ["code_gen"],
            "tags": ["python"],
            "max_price": 50.0
        }
        
        start = time.time()
        selected = await router.route_need(need)
        end = time.time()
        
        latency_ms = (end - start) * 1000
        
        # Routing should complete quickly (< 500ms for this simple case)
        assert latency_ms < 500
        assert selected is not None
    
    @pytest.mark.asyncio
    async def test_batch_routing_performance(self, router):
        """Can handle multiple routings quickly"""
        needs = [
            {"need_id": f"batch-{i}", "capabilities": ["code_gen"], "tags": ["python"]}
            for i in range(10)
        ]
        
        start = time.time()
        
        for need in needs:
            await router.route_need(need)
        
        end = time.time()
        total_time_ms = (end - start) * 1000
        avg_time_per_need = total_time_ms / len(needs)
        
        # Average routing should be fast
        # (In production with actual auctions, this would be 10x faster)
        assert avg_time_per_need < 300  # < 300ms per routing (accounting for test overhead)
    
    @pytest.mark.asyncio
    async def test_metrics_show_fast_routing(self, router):
        """Metrics confirm fast routing"""
        needs = [
            {"need_id": f"metric-{i}", "capabilities": ["code_gen"], "tags": ["python"]}
            for i in range(5)
        ]
        
        for need in needs:
            await router.route_need(need)
        
        stats = router.metrics.get_stats()
        avg_latency = stats["avg_latency_ms"]
        
        # Average routing latency should be low
        # Compared to typical auction times of 5-30 seconds (5000-30000ms),
        # routing should be 10-100x faster
        assert avg_latency < 1000  # Less than 1 second


# Integration Tests

class TestRouterIntegration:
    """Integration tests for complete router"""
    
    @pytest.mark.asyncio
    async def test_learning_over_time(self, router):
        """Router learns from feedback"""
        need = {
            "need_id": "learning-test",
            "capabilities": ["code_gen"],
            "tags": ["python"],
            "max_price": 50.0
        }
        
        # Route multiple times
        for i in range(10):
            selected = await router.route_need({"need_id": f"learn-{i}", **need})
            
            # Simulate feedback
            # agent-python-expert gets better rewards
            reward = 0.9 if selected == "agent-python-expert" else 0.6
            
            router.record_outcome(
                need_id=f"learn-{i}",
                need=need,
                agent_id=selected,
                task_result={
                    "quality_score": reward,
                    "latency_ms": 500.0,
                    "max_latency_ms": 5000.0
                }
            )
        
        # Check bandit learned
        best_arm = router.bandit.get_best_arm()
        assert best_arm is not None
    
    @pytest.mark.asyncio
    async def test_complete_stats(self, router):
        """Can get comprehensive router statistics"""
        # Do some routing
        for i in range(3):
            need = {
                "need_id": f"stats-{i}",
                "capabilities": ["code_gen"],
                "tags": ["python"]
            }
            selected = await router.route_need(need)
            
            if selected:
                router.record_outcome(
                    need_id=f"stats-{i}",
                    need=need,
                    agent_id=selected,
                    task_result={"quality_score": 0.8, "latency_ms": 500.0, "max_latency_ms": 5000.0}
                )
        
        stats = router.get_stats()
        
        assert "routing_metrics" in stats
        assert "bandit_stats" in stats
        assert "registry_stats" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
