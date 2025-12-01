"""
Intelligent Routing Module

Provides capability-based filtering, agent scoring, and intelligent routing
of tasks to the most suitable agents.
"""

from .manifests import AgentManifest, ManifestRegistry
from .filters import CapabilityFilter
from .scoring import AgentScorer, ScoredAgent
from .domain_fit import DomainFitCalculator
from .recency import RecencyWeighter
from .canary import CanaryTest, CanaryRunner, CanaryResult
from .winner_selection import WinnerSelector
from .bandit import ContextualBandit, ArmStats
from .features import FeatureExtractor
from .feedback import collect_feedback, FeedbackCollector
from .metrics import MetricsCollector, RoutingMetrics
from .router import IntelligentRouter

__all__ = [
    "AgentManifest",
    "ManifestRegistry",
    "CapabilityFilter",
    "AgentScorer",
    "ScoredAgent",
    "DomainFitCalculator",
    "RecencyWeighter",
    "CanaryTest",
    "CanaryRunner",
    "CanaryResult",
    "WinnerSelector",
    "ContextualBandit",
    "ArmStats",
    "FeatureExtractor",
    "collect_feedback",
    "FeedbackCollector",
    "MetricsCollector",
    "RoutingMetrics",
    "IntelligentRouter",
]
