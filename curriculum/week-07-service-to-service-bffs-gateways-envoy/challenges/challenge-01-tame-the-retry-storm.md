# Challenge 1 — Tame the Retry Storm

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. At 02:40 the `cart` service started returning a small fraction of 5xx — a transient blip, the kind a backend shrugs off twenty times a day. By 02:43 the *entire* cart path was down: 503s on every request, the backend pinned at 100% CPU, and the on-call before you had already "tried restarting Envoy," which made it worse for thirty seconds and then no better.

This is a **retry storm**. A small backend hiccup was amplified by a naive retry policy into a self-sustaining outage: the backend hiccuped, every request retried, the retry traffic tripled the load, the now-overloaded backend hiccuped harder, everyone retried again. The fault that started it is long gone; the retries are keeping the outage alive.

Your job: reproduce it, **prove from the stats that it's retry-driven** (not a backend bug, not a network partition), name the missing primitive, and fix it so the storm cannot re-form even under the same backend hiccup.

This mirrors the real skill. You rarely cause the storm in code you just wrote; you inherit it on a graph someone else built, and you have to find the off switch from the outside, under pressure, with `/stats` and a clear head.

## The harness

You need two pieces: a **flaky backend** (returns 5xx for a burst, then recovers) and an **Envoy with a naive retry policy** (no budget) in front of it. Save the backend as `flaky_backend.py`:

```python
#!/usr/bin/env python3
"""A gRPC-ish HTTP/2 backend that hiccups: healthy, then a 5-second burst of 5xx
under load, then healthy again. Stands in for 'cart' having a bad moment."""
import time
import threading
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# Shared state: are we in the hiccup window?
_state = {"hiccup_until": 0.0, "inflight": 0}
_lock = threading.Lock()


class FlakyHealth(health.HealthServicer):
    def Check(self, request, context):
        with _lock:
            _state["inflight"] += 1
            inflight = _state["inflight"]
            hiccuping = time.time() < _state["hiccup_until"]
        try:
            # The trigger: once concurrency crosses a threshold, start a hiccup
            # window. THIS is what a retry storm does — it pushes inflight up,
            # which triggers MORE failures, which triggers MORE retries.
            if inflight > 50 and not hiccuping:
                with _lock:
                    _state["hiccup_until"] = time.time() + 5.0
                hiccuping = True
            if hiccuping:
                context.abort(grpc.StatusCode.UNAVAILABLE, "backend hiccup")
            time.sleep(0.01)  # normal work
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.SERVING)
        finally:
            with _lock:
                _state["inflight"] -= 1


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=200))
    health_pb2_grpc.add_HealthServicer_to_server(FlakyHealth(), server)
    server.add_insecure_port("0.0.0.0:50051")
    server.start()
    print("flaky backend on :50051 — hiccups when inflight > 50")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
```

Save this **naive** Envoy config as `storm.yaml` — note it has `num_retries: 3` and **no retry budget**, which is the bug:

```yaml
admin:
  address: { socket_address: { address: 0.0.0.0, port_value: 9901 } }
static_resources:
  listeners:
  - name: ingress
    address: { socket_address: { address: 0.0.0.0, port_value: 10000 } }
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress
          route_config:
            name: edge
            virtual_hosts:
            - name: backend
              domains: ["*"]
              routes:
              - match: { prefix: "/" }
                route:
                  cluster: cart
                  timeout: 5s
                  retry_policy:
                    retry_on: "5xx,reset,connect-failure,unavailable"
                    num_retries: 3        # <-- up to 4x traffic, and...
                    # ...NO retry_budget. This is the planted fault. Retries are
                    # uncapped as a fraction of load, so they amplify the hiccup.
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
  clusters:
  - name: cart
    type: STRICT_DNS
    connect_timeout: 1s
    typed_extension_protocol_options:
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config: { http2_protocol_options: {} }
    load_assignment:
      cluster_name: cart
      endpoints:
      - lb_endpoints:
        - endpoint:
            address: { socket_address: { address: 127.0.0.1, port_value: 50051 } }
```

```bash
pip install grpcio grpcio-health-checking
python3 flaky_backend.py                 # terminal 1
func-e run -c storm.yaml                  # terminal 2
# terminal 3 — push it over the hiccup threshold:
ghz --insecure --call grpc.health.v1.Health.Check -c 80 -z 30s localhost:10000
```

Watch the client error rate spike and stay high. The hiccup was 5 seconds; the outage lasts the whole run. That gap is the storm.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — what the client sees (error rate, latency) and which `/stats` counters are climbing.
2. **Proof it's retry-driven** — the specific stats that distinguish a retry storm from a plain backend outage. (Hint: compare `upstream_rq_total` against the number of requests the *client* actually sent. In a storm, Envoy sends the backend far more requests than the client sent it — that multiplier IS the storm.)
3. **Root cause** — name the missing primitive in one sentence, as a property: "retries are uncapped as a fraction of active load, so a `p` fraction of failures becomes up to `4p` of load."
4. **Fix** — add a `retry_budget` (and explain your chosen `budget_percent`) and re-run. Show that under the *same* load, the hiccup now stays a hiccup: it does not become a sustained outage.
5. **Prevention** — one process change so this class of config never ships again.

You must reach the diagnosis with **at least two** independent signals — e.g., the request multiplier (`upstream_rq_total` vs client requests) *and* `upstream_rq_retry` climbing — not one. One signal is a guess; two is a diagnosis.

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You quantify the **amplification**: the ratio of `upstream_rq_total` to client-sent requests during the storm (it will be well above 1 — that excess is retries).
- [ ] Your fix adds a `retry_budget` (`budget_percent` + `min_retry_concurrency`) to the `cart` cluster's `circuit_breakers`. After the fix, `upstream_rq_retry_limit_exceeded` climbs under load — proof the budget is *refusing* the retries that previously formed the storm.
- [ ] You demonstrate, with two `ghz` runs (before/after), that the same load produces a sustained outage before and only a brief blip after.
- [ ] A `fixed.yaml` — the corrected config — checked in.
- [ ] Committed to your Week 7 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The tempting "fix" is to *lower `num_retries` to 1* or *remove retries entirely*. That stops the storm — by throwing away the resilience retries were supposed to provide. Now a single dropped packet is a client-visible error, which is the failure retries exist to mask. The *correct* fix keeps retries (they still recover transient failures) but **bounds them as a fraction of load** with a budget. The budget lets retries help in the small and refuses them in the large — exactly when amplification would otherwise kick in. Prescribing "turn off retries" is the wrong answer and you must not write it; it trades one failure mode for another.

A second trap: adding **outlier detection** here does little, because there's only *one* backend host — there's nowhere to route around to. Outlier detection helps when one of several hosts is bad; it doesn't help when your single backend is overloaded. Naming why outlier detection is the wrong tool *here* (one host, not a bad host) is worth saying in your writeup.

## Stretch

- Add a `per_try_timeout` and explain how an overly long per-try timeout *also* feeds the storm (slow tries hold connections, raising inflight, which is what triggers the backend's hiccup).
- Add a second backend host and turn on outlier detection. Now show a *different* failure (one bad host) where outlier detection IS the right tool — and contrast it with the storm, where it isn't.
- Reproduce the storm with `circuit_breakers.max_pending_requests` set low and show how fail-fast (a fast 503 from the breaker) is *gentler* on the backend than queuing — the breaker sheds load the backend would otherwise have to absorb.

## Why this matters

Every distributed system eventually has a hiccup. The question the postmortem asks is never "why did the backend hiccup" — backends always hiccup — it's "why did a 5-second hiccup become a 5-minute outage." The answer, more often than any other single cause, is uncapped retries. This challenge is that postmortem, rehearsed. When you defend your edge design in the gateway-vs-mesh memo and at the Phase 2 review, "every retry policy has a budget" is the line that tells a senior reviewer you've actually run an edge in anger.
