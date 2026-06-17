# Challenge 1 — The Trace That Stops at Kafka

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. The team shipped distributed tracing last sprint, and it works beautifully — for the synchronous path. A request from the BFF to `cart` to `inventory` is one clean trace in Tempo, every span nested correctly. But your `order.placed.v1` pipeline is *async*: `order` publishes the event to Kafka, and a separate `order-consumer` process picks it up and does the real fulfilment work. And there, in Tempo, the trace **shatters**: you see one trace that ends at the `publish order.placed.v1` span, and a *completely separate* trace that begins at `process order.placed.v1` — same wall-clock moment, same order ID in the logs, but two different trace IDs and no link between them.

During this morning's incident — orders stuck in "placed" but never fulfilled — you tried to follow one order from the BFF all the way to the consumer and *couldn't*. The trace died at Kafka. You had to fall back to grepping logs by order ID across two services, which is exactly the slow, error-prone debugging that tracing was supposed to end.

Your job: prove the trace is **splitting at the Kafka boundary** (and not breaking at gRPC or the mesh), name the exact mechanism, and fix it so one trace ID survives producer → consumer — **without** changing what the services do. "Just grep the logs" is not an answer; it's the problem you're paid to remove.

This mirrors the most common real distributed-tracing failure there is. HTTP and gRPC propagate trace context for free because the SDK auto-instrumentation owns a synchronous wire — it injects `traceparent` on the way out and extracts it on the way in. Kafka has *no* synchronous wire: the producer writes and moves on, the consumer reads later in a different process. Unless someone explicitly carries `traceparent` in the message headers, every async hop silently starts a fresh trace, and your end-to-end trace breaks at exactly the boundary where the hard bugs live.

## The harness

Reproduce it. Use the Exercise 3 script in its **broken** mode (`--no-propagate`), which models a producer that doesn't inject context — the real-world bug where someone wired the Kafka client without the OTel header propagation:

```bash
# Terminal A — the consumer (extracts context IF it's present in the headers):
python3 ../exercises/exercise-03-trace-context-across-kafka.py --consume

# Terminal B — the BROKEN producer: publishes WITHOUT injecting traceparent:
python3 ../exercises/exercise-03-trace-context-across-kafka.py --produce --no-propagate
```

Note the two **different** trace IDs the producer and consumer print. Now confirm the split in Tempo: search for both trace IDs and observe they are two separate, single-span traces instead of one two-span trace. You now have the bug. Diagnose it from the outside — from the trace data and the wire — before reading the fix section.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — exactly what you observe in Tempo: two traces where there should be one, the `publish` span as the leaf of one trace and the `process` span as the *root* of another (a span that is a root when it should be a child is the tell). Quote the two trace IDs.
2. **Proof it's the Kafka boundary, not gRPC or the mesh** — show that the *synchronous* hops (BFF→cart→inventory) DO join into one trace (so propagation works there), and that the break is precisely at the produce→consume hop. The contrast is the proof: if gRPC trace continuity is intact but the Kafka hop splits, the missing propagation is Kafka-specific, not a global SDK misconfiguration.
3. **The mechanism** — name it precisely: the consumer's span is a *root* (no parent) because the producer did not write `traceparent` into the Kafka message headers, so the consumer's `extract` found nothing to attach to and started a new trace. The async boundary has no wire for the SDK to auto-propagate across; it must be done in the message headers explicitly.
4. **The fix** — inject `traceparent` into the message headers on produce (and confirm the consumer's `extract` then finds it). Show the producer and consumer printing the **same** trace ID, and Tempo showing **one** trace with both spans. (Re-run Exercise 3 *without* `--no-propagate`.)
5. **Prevention** — one process change so async hops never silently break tracing again (e.g., "wrap every Kafka producer/consumer in a shared library that does inject/extract, so no team wires a raw client without propagation," or "a CI trace-continuity test that publishes and consumes a test event and asserts one trace ID").

You must reach the diagnosis with **at least two** independent signals — e.g., the two-different-trace-IDs observation *and* the consumer span being a root-with-no-parent, or the intact gRPC trace *and* the absent `traceparent` header on the Kafka message. One signal is a guess; two is a diagnosis.

## The fix, applied

The producer must inject context into the headers before sending:

```python
from opentelemetry.propagate import inject

with tracer.start_as_current_span("publish order.placed.v1") as span:
    headers = []
    inject(carrier=headers, setter=KafkaHeaderSetter())   # writes traceparent into the headers
    producer.produce(TOPIC, value=payload, headers=headers)
```

And the consumer must extract it and start its span as a child:

```python
from opentelemetry.propagate import extract

parent_ctx = extract(carrier=msg.headers(), getter=KafkaHeaderGetter())  # reads traceparent back
with tracer.start_as_current_span("process order.placed.v1", context=parent_ctx):
    ...   # now a CHILD of the producer's span: one trace across Kafka
```

Re-run, and the trace IDs match:

```bash
python3 ../exercises/exercise-03-trace-context-across-kafka.py --produce   # (propagation ON)
python3 ../exercises/exercise-03-trace-context-across-kafka.py --consume
# both print the SAME trace_id; Tempo shows one trace with both spans.
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You quote the **two different** trace IDs from the broken run, and show the consumer span is a *root* (no parent) when it should be a child.
- [ ] You demonstrate the **synchronous** path (gRPC) DOES form one trace — proving propagation works there and the break is Kafka-specific.
- [ ] You inspect the Kafka message and show `traceparent` is **absent** from the headers in the broken case and **present** after the fix.
- [ ] Your fix is the header inject/extract, NOT "grep logs by order ID." The producer and consumer print the same trace ID and Tempo shows one two-span trace.
- [ ] Committed to your Week 17 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Correlate by order ID in the logs instead."** This abandons tracing for the async path and re-introduces exactly the slow, manual, cross-service log-grepping that tracing exists to replace. It also doesn't compose: a trace ID threads metrics, traces, AND logs (the trace-to-log jump); an order ID only helps if every service logs it consistently, and it can't carry through services that don't know about orders. Falling back to log-grep is confirming the diagnosis (the trace is broken) and then giving up.
- **"Turn up sampling / restart Tempo."** The split is not a sampling or storage problem — both traces are stored fine; they're just *unlinked*. Sampling changes how many traces you keep, not whether two halves of one trace join. Restarting Tempo changes nothing because Tempo is faithfully storing exactly what it received: two separate traces, because that's what the producer/consumer emitted. The bug is upstream, in the propagation, not in the backend.

A related real-world cousin worth naming in your writeup: the **in-process context loss** — a service that DOES propagate across Kafka but starts its outbound call with a fresh `context.Background()` instead of the inbound request's context, orphaning the child span *within* one service. Same family (lost context), different boundary (in-process vs cross-process), and the same tell (a span that's a root when it should be a child).

## Stretch

- Reproduce the **in-process** version: in the consumer, start a downstream gRPC call with a fresh context instead of the span's context, and watch *that* hop orphan even though Kafka propagation is correct. Fix it by threading the context through. Explain why both bugs produce the same "root span where a child belongs" symptom.
- Add a **trace-continuity CI test**: a tiny harness that produces a test event with a known trace ID, consumes it, and asserts (via the Tempo API) that one trace contains both spans. Make it fail when you flip back to `--no-propagate`. This is the prevention from part 5, made real.
- Propagate **baggage** alongside `traceparent` across Kafka (e.g. a `tenant.id`), and confirm the consumer can read it off the context without re-fetching. Note the per-message cost of fat baggage.

## Why this matters

Every tracing rollout hits this wall: the synchronous paths trace beautifully, the team declares victory, and then the first hard incident is in an async pipeline where the trace shatters at every Kafka hop — and tracing, the tool that was supposed to make the incident fast, is useless exactly when it's needed. The difference between a tracing program that survives and one that gets abandoned is whether *someone* can look at two disconnected traces and say "we're not propagating context across the queue; here's the header inject, the trace is one piece again." When you defend your `cart-observed` mini-project — and when you trace an order end-to-end through the capstone's `order.placed.v1` spine — "I know exactly why a trace breaks at an async boundary and how to make it survive" is the line that says you've operated tracing, not just installed it.
