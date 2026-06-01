"""OpenTelemetry setup for traces + logs + metrics (Phase 5).

Targets Aspire Dashboard via OTLP gRPC on `OTEL_ENDPOINT`
(default `http://localhost:4317`). Start the backend with:

    bash scripts/run_observability.sh

`setup_otel(app=None, service_suffix=None)` is idempotent. It probes
the endpoint at startup and self-disables (logs a warning) when
Aspire isn't reachable, so a stopped backend never breaks the app.
"""
import logging
import socket
from typing import Any
from urllib.parse import urlparse

from app.config import settings

_INSTALLED = False
_log = logging.getLogger(__name__)


def _backend_reachable(timeout_s: float = 1.0) -> bool:
    """TCP-probe the OTLP endpoint; skip OTel init if no one's home."""
    parsed = urlparse(settings.otel_endpoint)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4317
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


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
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    return OTLPSpanExporter(
        endpoint=settings.otel_endpoint, insecure=True
    )


def _log_exporter():
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
        OTLPLogExporter,
    )

    return OTLPLogExporter(
        endpoint=settings.otel_endpoint, insecure=True
    )


def _metric_exporter():
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )

    return OTLPMetricExporter(
        endpoint=settings.otel_endpoint, insecure=True
    )


def _setup_traces(resource) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(_trace_exporter()))
    trace.set_tracer_provider(provider)


_OTEL_HANDLER_FLAG = "_otel_managed_handler"


def _setup_logs(resource) -> None:
    """Attach exactly one OTLP log handler to the root logger.

    If this is somehow called a second time within the same process
    (e.g. a uvicorn --reload edge case, a stray re-import, a script
    that imports the API module), the prior handler is left in place
    and we no-op. Without this guard each log record gets shipped to
    Aspire twice - identical trace_id, identical timestamp, two rows.
    """
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    root_logger = logging.getLogger()
    if any(
        getattr(h, _OTEL_HANDLER_FLAG, False)
        for h in root_logger.handlers
    ):
        _log.debug(
            "OTel log handler already attached; skipping re-attach"
        )
        return

    provider = LoggerProvider(resource=resource)
    set_logger_provider(provider)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(_log_exporter())
    )
    handler = LoggingHandler(
        level=logging.INFO, logger_provider=provider
    )
    setattr(handler, _OTEL_HANDLER_FLAG, True)
    root_logger.addHandler(handler)


def _setup_metrics(resource) -> None:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        PeriodicExportingMetricReader,
    )

    reader = PeriodicExportingMetricReader(
        _metric_exporter(),
        export_interval_millis=5000,
    )
    provider = MeterProvider(
        resource=resource, metric_readers=[reader]
    )
    metrics.set_meter_provider(provider)


def _instrument_fastapi(app: Any) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def _instrument_httpx() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def _instrument_logging() -> None:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument(set_logging_format=False)


def _instrument_langchain() -> None:
    """OpenInference auto-instrumentor for LangChain.

    Emits OTel spans for every chain / LLM / embedding / retriever
    invocation, including prompt + completion previews, model name,
    token usage. Renders as Langfuse-style detail in Aspire.
    """
    try:
        from openinference.instrumentation.langchain import (
            LangChainInstrumentor,
        )
    except ImportError:
        _log.warning(
            "openinference-instrumentation-langchain not installed; "
            "LangChain spans (prompt/completion detail) won't appear. "
            "Reinstall: pip install -r requirements.txt"
        )
        return
    LangChainInstrumentor().instrument()


def annotate_request_span(
    span,
    *,
    user_id: str | None = None,
    conversation_id: int | None = None,
) -> None:
    """Tag a span with user.id and conversation.id when known.

    Safe to call with None values - the corresponding attribute is just
    skipped. Use from route handlers (root HTTP span) and from each
    graph node so the IDs are visible everywhere in Aspire.
    """
    if span is None:
        return
    if user_id:
        span.set_attribute("user.id", str(user_id))
    if conversation_id:
        try:
            span.set_attribute("conversation.id", int(conversation_id))
        except (TypeError, ValueError):
            pass


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

    if not _backend_reachable():
        _log.warning(
            "OTel enabled but backend at %s is unreachable - "
            "skipping setup. Start Aspire with "
            "`bash scripts/run_observability.sh` (or use run_all.sh) "
            "and restart this process.",
            settings.otel_endpoint,
        )
        return

    try:
        resource = _resource(service_suffix)
        _setup_traces(resource)
        _setup_logs(resource)
        _setup_metrics(resource)
        _instrument_logging()
        _instrument_httpx()
        _instrument_langchain()
        if app is not None:
            _instrument_fastapi(app)
        _INSTALLED = True
        _log.info(
            "OTel enabled: endpoint=%s service=%s ui=%s",
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
