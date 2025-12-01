"""
Distributed tracing with OpenTelemetry.

Provides utilities for creating traces across the agent swarm,
enabling observability of message flows and task execution.
"""

import logging
from typing import Dict, Any, Optional, ContextManager
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode, Span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_tracer_provider: Optional[TracerProvider] = None


def setup_tracing(
    service_name: str, otlp_endpoint: Optional[str] = None, console_export: bool = False
) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing for the service.

    Args:
        service_name: Name of the service (e.g., "agent-swarm", "verifier-1")
        otlp_endpoint: OTLP collector endpoint (e.g., "http://localhost:4317")
                      If None, uses environment variable OTEL_EXPORTER_OTLP_ENDPOINT
        console_export: If True, also export spans to console for debugging

    Returns:
        Configured tracer instance
    """
    global _tracer, _tracer_provider

    # Create resource with service name
    resource = Resource(attributes={SERVICE_NAME: service_name})

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Add OTLP exporter if endpoint provided
    if otlp_endpoint or console_export:
        if otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"Configured OTLP exporter: {otlp_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to configure OTLP exporter: {e}")

        if console_export:
            console_exporter = ConsoleSpanExporter()
            _tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
            logger.info("Configured console span exporter")

    # Set global tracer provider
    trace.set_tracer_provider(_tracer_provider)

    # Create tracer
    _tracer = trace.get_tracer(__name__)

    logger.info(f"Initialized tracing for service: {service_name}")

    return _tracer


def get_tracer() -> trace.Tracer:
    """
    Get the global tracer instance.

    Returns:
        Tracer instance

    Raises:
        RuntimeError: If tracing not initialized
    """
    if _tracer is None:
        raise RuntimeError("Tracing not initialized. Call setup_tracing() first.")
    return _tracer


@contextmanager
def create_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> ContextManager[Span]:
    """
    Create a trace span with optional attributes.

    Usage:
        with create_span("process_message", {"message_id": "123"}):
            # Do work
            pass

    Args:
        name: Span name (e.g., "publish_message", "execute_task")
        attributes: Optional span attributes
        kind: Span kind (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER)

    Yields:
        Active span
    """
    tracer = get_tracer()

    with tracer.start_as_current_span(name, kind=kind) as span:
        # Add attributes if provided
        if attributes:
            for key, value in attributes.items():
                # Convert value to string if needed
                if value is not None:
                    span.set_attribute(key, str(value))

        try:
            yield span
        except Exception as e:
            # Record exception in span
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def get_current_span() -> Span:
    """
    Get the currently active span.

    Returns:
        Current span or INVALID_SPAN if no active span
    """
    return trace.get_current_span()


def propagate_context(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inject trace context into a message envelope.

    This allows trace propagation across service boundaries.
    The trace context is added to the envelope's metadata.

    Args:
        envelope: Message envelope to inject context into

    Returns:
        Envelope with trace context in metadata
    """
    # Get current span context
    current_span = get_current_span()

    if current_span and current_span.is_recording():
        # Create carrier for context propagation
        carrier = {}

        # Inject context into carrier
        propagator = TraceContextTextMapPropagator()
        propagator.inject(carrier)

        # Add trace context to envelope metadata
        if "metadata" not in envelope:
            envelope["metadata"] = {}

        envelope["metadata"]["trace_context"] = carrier

        # Also add trace_id for easier debugging
        trace_id = format(current_span.get_span_context().trace_id, "032x")
        envelope["metadata"]["trace_id"] = trace_id

    return envelope


def extract_context(envelope: Dict[str, Any]) -> Optional[trace.SpanContext]:
    """
    Extract trace context from a message envelope.

    This allows continuing a trace across service boundaries.

    Args:
        envelope: Message envelope containing trace context

    Returns:
        Span context if found, None otherwise
    """
    # Check if envelope has trace context
    metadata = envelope.get("metadata", {})
    trace_context = metadata.get("trace_context")

    if not trace_context:
        return None

    # Extract context from carrier
    propagator = TraceContextTextMapPropagator()
    context = propagator.extract(trace_context)

    # Get span context from extracted context
    span = trace.get_current_span(context)
    return span.get_span_context() if span else None


def start_span_from_context(
    name: str,
    envelope: Dict[str, Any],
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.CONSUMER,
) -> ContextManager[Span]:
    """
    Start a span as a child of the trace context in the envelope.

    This is used when receiving a message to continue the distributed trace.

    Args:
        name: Span name
        envelope: Message envelope with trace context
        attributes: Optional span attributes
        kind: Span kind

    Returns:
        Context manager for the span
    """
    tracer = get_tracer()

    # Extract parent context
    trace_context = envelope.get("metadata", {}).get("trace_context")

    # Create span with parent context if available
    if trace_context:
        propagator = TraceContextTextMapPropagator()
        parent_context = propagator.extract(trace_context)

        return tracer.start_as_current_span(
            name, context=parent_context, kind=kind, attributes=attributes
        )
    else:
        # No parent context, create root span
        return tracer.start_as_current_span(name, kind=kind, attributes=attributes)


def shutdown_tracing():
    """
    Shutdown tracing and flush all pending spans.

    Should be called before application exit.
    """
    global _tracer_provider

    if _tracer_provider:
        _tracer_provider.shutdown()
        logger.info("Tracing shutdown complete")
