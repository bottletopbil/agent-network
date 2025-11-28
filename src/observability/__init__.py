"""
Observability module for distributed tracing and monitoring.

Provides OpenTelemetry integration for the agent swarm.
"""

from .tracing import (
    setup_tracing,
    create_span,
    get_current_span,
    propagate_context,
    extract_context,
    get_tracer
)

__all__ = [
    'setup_tracing',
    'create_span',
    'get_current_span',
    'propagate_context',
    'extract_context',
    'get_tracer'
]
