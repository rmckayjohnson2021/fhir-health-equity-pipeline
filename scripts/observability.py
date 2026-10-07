"""Small OpenTelemetry helpers for optional local console tracing."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any


class NullSpan:
    def add_event(self, _name: str, _attributes: dict[str, Any] | None = None) -> None:
        return

    def record_exception(self, _exception: BaseException) -> None:
        return

    def set_attribute(self, _key: str, _value: Any) -> None:
        return

    def set_status(self, _status: Any) -> None:
        return


def configure_console_tracing(enabled: bool, service_name: str) -> Any | None:
    if not enabled:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
    except ImportError as error:
        raise RuntimeError(
            "OpenTelemetry console tracing requires the opentelemetry-sdk package. "
            "Run `uv sync` to install project dependencies."
        ) from error

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def start_span(tracer: Any | None, name: str, attributes: dict[str, Any] | None = None) -> Any:
    if tracer is None:
        return nullcontext(NullSpan())
    return tracer.start_as_current_span(name, attributes=sanitize_attributes(attributes or {}))


def sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            clean[key] = "unknown"
        elif isinstance(value, (str, bool, int, float)):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


def mark_error(span: Any, reason: str, exception: BaseException | None = None) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:
        return

    if exception is not None:
        span.record_exception(exception)
    span.set_status(Status(StatusCode.ERROR, reason))
