"""OpenTelemetry setup for traces + logs (Phase 5).

Supports two OTLP protocols, picked by `OTEL_PROTOCOL`:
  - "grpc" (default): full endpoint URL is `OTEL_ENDPOINT`
    Pairs well with Aspire Dashboard or Jaeger (port 4317).
  - "http": `OTEL_ENDPOINT` is treated as a base URL; `/v1/traces` and
    `/v1/logs` are appended automatically. Pairs well with OpenObserve
    (set `OTEL_ENDPOINT=http://localhost:5080/api/default`).

`setup_otel(app=None, service_suffix=None)` is idempotent and a no-op
when `OTEL_ENABLED=false`.
"""
import logging
from typing import Any

from app.config import settings

_INSTALLED = False
_log = logging.getLogger(__name__)


def _parse_headers(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _resource(service_suffix: str | None):
    from opentelemetry.sdk.resources import Resource

    name = settings.otel_service_name
    if service_suffix:
        name = f"{name}-{service_suffix}"
    return Resource.create(
        {
            "service.name": name,
            "service.version": "0.5.0",
        }
    )


def _trace_exporter():
    headers = _parse_headers(settings.otel_headers)
    if settings.otel_protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = settings.otel_endpoint.rstrip("/") + "/v1/traces"
        kwargs: dict[str, Any] = {"endpoint": endpoint}
        if headers:
            kwargs["headers"] = headers
        return OTLPSpanExporter(**kwargs)
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    kwargs = {"endpoint": settings.otel_endpoint, "insecure": True}
    if headers:
        kwargs["headers"] = headers
    return OTLPSpanExporter(**kwargs)


def _log_exporter():
    headers = _parse_headers(settings.otel_headers)
    if settings.otel_protocol == "http":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (
            OTLPLogExporter,
        )

        endpoint = settings.otel_endpoint.rstrip("/") + "/v1/logs"
        kwargs: dict[str, Any] = {"endpoint": endpoint}
        if headers:
            kwargs["headers"] = headers
        return OTLPLogExporter(**kwargs)
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
        OTLPLogExporter,
    )

    kwargs = {"endpoint": settings.otel_endpoint, "insecure": True}
    if headers:
        kwargs["headers"] = headers
    return OTLPLogExporter(**kwargs)


def _setup_traces(resource) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(_trace_exporter()))
    trace.set_tracer_provider(provider)


def _setup_logs(resource) -> None:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=resource)
    set_logger_provider(provider)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(_log_exporter())
    )
    handler = LoggingHandler(
        level=logging.INFO, logger_provider=provider
    )
    logging.getLogger().addHandler(handler)


def _instrument_fastapi(app: Any) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def _instrument_httpx() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def _instrument_logging() -> None:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument(set_logging_format=False)


def setup_otel(
    app: Any | None = None,
    service_suffix: str | None = None,
) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if not settings.otel_enabled:
        _log.info("OTel disabled (OTEL_ENABLED=false)")
        return

    try:
        resource = _resource(service_suffix)
        _setup_traces(resource)
        _setup_logs(resource)
        _instrument_logging()
        _instrument_httpx()
        if app is not None:
            _instrument_fastapi(app)
        _INSTALLED = True
        _log.info(
            "OTel enabled: protocol=%s endpoint=%s service=%s ui=%s",
            settings.otel_protocol,
            settings.otel_endpoint,
            settings.otel_service_name
            + (f"-{service_suffix}" if service_suffix else ""),
            settings.otel_ui_url,
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("OTel setup failed: %s", exc)


def get_tracer(name: str):
    """Return a tracer (no-op if OTel is disabled)."""
    from opentelemetry import trace

    return trace.get_tracer(name)
