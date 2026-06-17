#!/usr/bin/env python3
# Exercise 3 — Trace Context Across the Kafka Boundary (runnable)
#
# Goal: Propagate the W3C `traceparent` across a Kafka producer->consumer boundary so
#       ONE distributed trace survives the async hop, and PROVE it: the consumer's
#       span is a CHILD of the producer's span, in the SAME trace, visible as one
#       trace in Tempo.
#
#       This is the boundary that breaks SILENTLY. HTTP/gRPC auto-instrumentation
#       injects/extracts traceparent for you because they own a synchronous wire.
#       Kafka has no synchronous wire — the producer writes and moves on; the
#       consumer reads later, in a DIFFERENT process. Unless you carry traceparent
#       in the MESSAGE HEADERS yourself, the trace splits in two: a producer trace
#       that ends at "published" and an unrelated consumer trace that starts at
#       "consumed." This script does the inject (produce) and extract (consume).
#
# Estimated time: 60 minutes. Runnable.
#
# HOW THIS EXERCISE WORKS
#   Run the PRODUCER in one terminal and the CONSUMER in another. The producer
#   starts a trace, injects traceparent into the Kafka message headers, and prints
#   the trace ID it used. The consumer extracts traceparent from the headers, starts
#   its span as a CHILD, and prints the SAME trace ID. You then look up that one
#   trace ID in Tempo and see BOTH spans in one trace, across the boundary.
#
#   STEP 1 (terminal A):  python3 exercise-03-trace-context-across-kafka.py --consume
#   STEP 2 (terminal B):  python3 exercise-03-trace-context-across-kafka.py --produce
#   STEP 3:               look the printed trace ID up in Tempo; confirm 2 spans, 1 trace.
#
#   To SEE THE BUG, run with --no-propagate on the producer: the consumer then
#   starts a NEW, unrelated trace (different trace ID) — the split this exercise prevents.
#
# PREREQUISITES
#   - Kafka or Redpanda reachable (KAFKA_BOOTSTRAP, default localhost:9092) with a
#     topic `order.placed.v1` (auto-create or `kafka-topics --create`).
#   - The OTel Collector reachable at OTEL_EXPORTER_OTLP_ENDPOINT (default
#     http://localhost:4317) exporting traces to Tempo (Exercise 1).
#   - pip install confluent-kafka opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
#
# The propagation logic (inject/extract + the header setter/getter) is the whole
# point — read it. Everything else is plumbing.

import argparse
import os
import sys
import time
import json

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject, extract, set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagators.textmap import Setter, Getter

from confluent_kafka import Producer, Consumer

TOPIC = "order.placed.v1"
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
OTLP = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def init_tracing(service_name: str):
    """One tracer provider per process; install the W3C propagator (the load-bearing line)."""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP, insecure=True)))
    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())
    return trace.get_tracer(service_name)


# --- The setter/getter that read and write Kafka's byte-pair headers ---------
# Kafka headers are a list of (key: str, value: bytes) tuples. The propagator
# speaks strings, so we encode/decode utf-8 at the boundary.

class KafkaHeaderSetter(Setter):
    def set(self, carrier: list, key: str, value: str) -> None:
        # remove any existing key, then append (headers can repeat; keep it clean)
        carrier[:] = [(k, v) for (k, v) in carrier if k != key]
        carrier.append((key, value.encode("utf-8")))


class KafkaHeaderGetter(Getter):
    def get(self, carrier: list, key: str):
        if carrier is None:
            return None
        return [v.decode("utf-8") for (k, v) in carrier if k == key] or None

    def keys(self, carrier: list):
        return [k for (k, _) in (carrier or [])]


_setter = KafkaHeaderSetter()
_getter = KafkaHeaderGetter()


# --- PRODUCER: start a trace, INJECT traceparent into the Kafka headers -------

def produce(propagate: bool) -> int:
    tracer = init_tracing("order")           # the producing service
    producer = Producer({"bootstrap.servers": BOOTSTRAP})

    with tracer.start_as_current_span("publish order.placed.v1") as span:
        span.set_attribute("messaging.system", "kafka")            # semantic convention
        span.set_attribute("messaging.destination.name", TOPIC)
        span.set_attribute("messaging.operation", "publish")

        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")
        print(f"[producer] trace_id = {trace_id}")

        headers: list = []
        if propagate:
            # THE FIX: write traceparent (and tracestate) into the message headers,
            # so the consumer — a different process — can join THIS trace.
            inject(carrier=headers, setter=_setter)
            print(f"[producer] injected headers: {[(k, v.decode()) for k, v in headers]}")
        else:
            # --no-propagate: the bug. No traceparent in the headers -> the consumer
            # cannot join this trace -> the trace SPLITS at Kafka.
            print("[producer] NOT propagating (the bug): consumer will start a NEW trace")

        payload = json.dumps({"order_id": "o-123", "cart_id": "abc"}).encode("utf-8")
        producer.produce(TOPIC, value=payload, headers=headers)
        producer.flush(5)

    # let the batch span processor flush to the Collector before we exit
    trace.get_tracer_provider().force_flush()
    time.sleep(2)
    print("[producer] published. Look up the trace_id above in Tempo.")
    return 0


# --- CONSUMER: EXTRACT traceparent, start the span as a CHILD -----------------

def consume() -> int:
    tracer = init_tracing("order-consumer")  # a DIFFERENT process / service
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": "trace-demo",
        "auto.offset.reset": "latest",
    })
    consumer.subscribe([TOPIC])
    print("[consumer] waiting for a message on", TOPIC, "...")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print("[consumer] kafka error:", msg.error(), file=sys.stderr)
                continue

            # THE FIX (consumer side): read traceparent back out of the headers and
            # build the parent context, so our span attaches to the PRODUCER's trace.
            incoming = msg.headers() or []
            parent_ctx = extract(carrier=incoming, getter=_getter)

            with tracer.start_as_current_span(
                "process order.placed.v1", context=parent_ctx
            ) as span:
                span.set_attribute("messaging.system", "kafka")
                span.set_attribute("messaging.operation", "process")
                trace_id = format(span.get_span_context().trace_id, "032x")
                print(f"[consumer] trace_id = {trace_id}  (should MATCH the producer's)")
                # ... real handler work would go here ...
                time.sleep(0.05)

            trace.get_tracer_provider().force_flush()
            break  # one message is enough to prove it
    finally:
        consumer.close()
    print("[consumer] done. The trace_id above must equal the producer's -> one trace across Kafka.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace context across the Kafka boundary.")
    parser.add_argument("--produce", action="store_true", help="produce a message (injects traceparent)")
    parser.add_argument("--consume", action="store_true", help="consume a message (extracts traceparent)")
    parser.add_argument("--no-propagate", action="store_true",
                        help="produce WITHOUT injecting traceparent (demonstrates the split-trace bug)")
    args = parser.parse_args()

    if args.produce:
        return produce(propagate=not args.no_propagate)
    if args.consume:
        return consume()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   # Terminal A (consumer), then Terminal B (producer):
#   $ python3 exercise-03-trace-context-across-kafka.py --produce
#   [producer] trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
#   [producer] injected headers: [('traceparent', '00-4bf92f35...-00f067aa0ba902b7-01')]
#   [producer] published. Look up the trace_id above in Tempo.
#
#   $ python3 exercise-03-trace-context-across-kafka.py --consume
#   [consumer] trace_id = 4bf92f3577b34da6a3ce929d0e0e4736   (should MATCH the producer's)
#   [consumer] done. ... one trace across Kafka.
#
#   # The trace IDs MATCH. In Tempo, that one trace contains BOTH spans:
#   $ curl -s "http://localhost:3200/api/traces/4bf92f3577b34da6a3ce929d0e0e4736" \
#       | jq '[.batches[].scopeSpans[].spans[].name]'
#   [ "publish order.placed.v1", "process order.placed.v1" ]    <-- two spans, ONE trace
#
#   # Now the BUG, for contrast:
#   $ python3 exercise-03-trace-context-across-kafka.py --produce --no-propagate
#   [producer] trace_id = aaaa...                # one ID
#   $ python3 exercise-03-trace-context-across-kafka.py --consume
#   [consumer] trace_id = bbbb...                # a DIFFERENT ID -> the trace SPLIT at Kafka
#
# THE LESSON: HTTP/gRPC propagate traceparent for free because the SDK owns the wire.
# Kafka does NOT — you must inject on produce and extract on consume, carrying
# traceparent in the message headers. The trace that "stops at Kafka" is never a
# Kafka or Tempo bug; it is a missing inject or extract. This is the single most
# valuable propagation skill of the week, and the subject of Challenge 1.
#
# ACCEPTANCE CRITERIA
#   [ ] With propagation ON, the producer and consumer print the SAME trace_id.
#   [ ] Tempo shows ONE trace containing BOTH the publish and process spans.
#   [ ] With --no-propagate, the consumer prints a DIFFERENT trace_id (the split).
#   [ ] You can explain WHY Kafka needs manual propagation while HTTP/gRPC do not.
#   [ ] The consumer span is a CHILD of the producer span (parent/child, not two roots).
# -----------------------------------------------------------------------------
