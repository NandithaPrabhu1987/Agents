import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


def setup_tracing(app=None):
    # Phoenix default OTLP HTTP endpoint
    endpoint = os.getenv("PHOENIX_OTLP_HTTP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "inventory-agent"),
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Instrument FastAPI app and outbound HTTPX calls (Groq SDK uses httpx)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
