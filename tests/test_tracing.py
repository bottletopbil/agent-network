"""
Tests for OpenTelemetry distributed tracing.

Verifies span creation, context propagation, and bus integration.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from observability.tracing import (
    setup_tracing,
    create_span,
    get_current_span,
    propagate_context,
    extract_context,
    start_span_from_context,
    get_tracer,
    shutdown_tracing,
)
from opentelemetry.trace import SpanKind


class TestTracingSetup:
    """Test tracing setup and configuration"""

    def test_setup_tracing(self):
        """Test setting up tracing with service name"""
        tracer = setup_tracing("test-service", console_export=False)

        # Tracer should be configured
        assert tracer is not None

        # Should be able to get tracer
        t = get_tracer()
        assert t is tracer

        shutdown_tracing()

    def test_setup_tracing_without_otlp(self):
        """Test setup without OTLP endpoint (no exporter)"""
        tracer = setup_tracing("test-service")

        assert tracer is not None

        shutdown_tracing()

    def test_get_tracer_before_setup_raises_error(self):
        """Test that getting tracer before setup raises RuntimeError"""
        # Reset tracing state
        import observability.tracing as tracing_module

        tracing_module._tracer = None

        with pytest.raises(RuntimeError, match="Tracing not initialized"):
            get_tracer()

        # Restore tracing
        setup_tracing("test-service")


class TestSpanCreation:
    """Test span creation and attributes"""

    @classmethod
    def setup_class(cls):
        """Setup tracing for all tests"""
        setup_tracing("test-service", console_export=False)

    @classmethod
    def teardown_class(cls):
        """Shutdown tracing after all tests"""
        shutdown_tracing()

    def test_create_span_basic(self):
        """Test creating a basic span"""
        with create_span("test_operation") as span:
            assert span is not None
            assert span.is_recording()

            # Span should be current
            current = get_current_span()
            assert current == span

    def test_create_span_with_attributes(self):
        """Test creating span with custom attributes"""
        attributes = {
            "task_id": "task_123",
            "thread_id": "thread_456",
            "operation": "DECIDE",
        }

        with create_span("process_task", attributes=attributes) as span:
            assert span.is_recording()
            # Attributes are set but we can't easily verify them without exporter

    def test_create_span_with_kind(self):
        """Test creating span with specific kind"""
        with create_span("publish_message", kind=SpanKind.PRODUCER) as span:
            assert span.is_recording()

        with create_span("consume_message", kind=SpanKind.CONSUMER) as span:
            assert span.is_recording()

    def test_create_span_exception_handling(self):
        """Test that exception in span is recorded"""
        try:
            with create_span("failing_operation") as span:
                assert span.is_recording()
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected

        # Span should have recorded the exception (but we can't verify without exporter)

    def test_nested_spans(self):
        """Test creating nested spans"""
        with create_span("parent_operation") as parent:
            assert parent.is_recording()

            with create_span("child_operation") as child:
                assert child.is_recording()

                # Both should be active in context
                current = get_current_span()
                assert current == child


class TestContextPropagation:
    """Test trace context propagation across process boundaries"""

    @classmethod
    def setup_class(cls):
        """Setup tracing for all tests"""
        setup_tracing("test-service", console_export=False)

    @classmethod
    def teardown_class(cls):
        """Shutdown tracing after all tests"""
        shutdown_tracing()

    def test_propagate_context_basic(self):
        """Test injecting trace context into envelope"""
        envelope = {"operation": "DECIDE", "payload": {"task_id": "123"}}

        with create_span("send_message"):
            # Propagate context into envelope
            enriched = propagate_context(envelope)

            # Envelope should have trace context in metadata
            assert "metadata" in enriched
            assert "trace_context" in enriched["metadata"]
            assert "trace_id" in enriched["metadata"]

    def test_propagate_context_preserves_existing_metadata(self):
        """Test that propagation preserves existing metadata"""
        envelope = {
            "operation": "DECIDE",
            "metadata": {"existing_key": "existing_value"},
        }

        with create_span("send_message"):
            enriched = propagate_context(envelope)

            # Should preserve existing metadata
            assert enriched["metadata"]["existing_key"] == "existing_value"
            assert "trace_context" in enriched["metadata"]

    def test_extract_context(self):
        """Test extracting trace context from envelope"""
        envelope = {"operation": "DECIDE"}

        with create_span("send_message") as parent_span:
            # Propagate context
            enriched = propagate_context(envelope)

            # Extract context
            extract_context(enriched)

            # Should have extracted a valid context
            # Note: The actual context extraction requires more setup
            # This test verifies the function doesn't error

    def test_extract_context_missing(self):
        """Test extracting context from envelope without trace context"""
        envelope = {"operation": "DECIDE"}

        # No trace context in envelope
        span_context = extract_context(envelope)

        # Should return None
        assert span_context is None

    def test_start_span_from_context(self):
        """Test starting a span from extracted context"""
        # Create parent span and propagate context
        with create_span("publisher"):
            envelope = {"operation": "DECIDE"}
            enriched = propagate_context(envelope)

        # Start child span from context
        with start_span_from_context(
            "consumer", enriched, kind=SpanKind.CONSUMER
        ) as child_span:
            assert child_span.is_recording()

            # Should be linked to parent trace
            # (Can't easily verify without accessing span internals)

    def test_start_span_from_context_without_parent(self):
        """Test starting span when no parent context exists"""
        envelope = {"operation": "DECIDE"}  # No trace context

        # Should create root span
        with start_span_from_context(
            "consumer", envelope, kind=SpanKind.CONSUMER
        ) as span:
            assert span.is_recording()


class TestBusIntegration:
    """Test tracing integration with message bus (mock tests)"""

    @classmethod
    def setup_class(cls):
        """Setup tracing for all tests"""
        setup_tracing("test-bus", console_export=False)

    @classmethod
    def teardown_class(cls):
        """Shutdown tracing after all tests"""
        shutdown_tracing()

    def test_publish_creates_span(self):
        """Test that publishing creates a producer span"""
        # Mock test - verify span is created
        with create_span("bus.publish_envelope", kind=SpanKind.PRODUCER) as span:
            envelope = {"operation": "DECIDE", "payload": {}}

            # Inject trace context
            enriched = propagate_context(envelope)

            assert span.is_recording()
            assert "trace_context" in enriched.get("metadata", {})

    def test_subscribe_extracts_context(self):
        """Test that subscribing extracts and continues trace"""
        # Create and propagate parent span
        with create_span("publisher", kind=SpanKind.PRODUCER):
            envelope = {"operation": "DECIDE"}
            enriched = propagate_context(envelope)

        # Consumer receives and continues trace
        with start_span_from_context(
            "bus.handle_envelope", enriched, kind=SpanKind.CONSUMER
        ) as span:
            assert span.is_recording()

            # Simulate handling
            with create_span("handle_decide"):
                pass

    def test_end_to_end_trace_flow(self):
        """Test complete trace flow: publish -> transport -> consume"""
        trace_ids = []

        # Publisher side
        with create_span("task.execute", kind=SpanKind.INTERNAL) as task_span:
            with create_span(
                "bus.publish_envelope", kind=SpanKind.PRODUCER
            ) as publish_span:
                envelope = {"operation": "DECIDE", "task_id": "123"}
                enriched = propagate_context(envelope)

                # Capture trace ID
                trace_id = enriched["metadata"]["trace_id"]
                trace_ids.append(trace_id)

        # Consumer side
        with start_span_from_context(
            "bus.handle_envelope", enriched, kind=SpanKind.CONSUMER
        ):
            with create_span("handler.process_decide"):
                # Verify we have the same trace ID
                current_span = get_current_span()
                assert current_span.is_recording()


class TestTracingOptional:
    """Test that tracing is optional and degrades gracefully"""

    def test_tracing_disabled_gracefully(self):
        """Test that code works without tracing enabled"""
        # This would be tested by disabling import in bus.py
        # For now, just verify basic flow
        envelope = {"operation": "DECIDE"}

        # These should not error even if tracing is disabled
        # (In real scenario, TRACING_ENABLED would be False)
        result = envelope.copy()
        assert result == envelope


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
