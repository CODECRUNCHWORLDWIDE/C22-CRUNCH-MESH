# Exercise 1 — Trace One Order End to End

**Goal:** Place a single order through your running Polyglot Marketplace Backbone and follow it through *every* hop — BFF → order → cart → inventory → payment → Kafka → search — ending in a trace-to-log jump. This is the demo's architecture-walk segment, the proof the backbone is actually wired together, and the rehearsal for the highest-stakes ninety seconds of Friday's defense. You will train the single most important capstone-demo habit: showing the system *running and observable*, not describing it.

**Estimated time:** 60 minutes. Guided.

---

## Setup

You need the backbone up in at least one region, with the OpenTelemetry pipeline (Tempo for traces, Loki for logs, Grafana to view them) running.

```bash
kubectl --context kind-region-primary get pods -n shop
# all services Running and Ready (cart, inventory, payment, order, search, bffs)
kubectl --context kind-region-primary get pods -n observability
# tempo, loki, grafana, prometheus Running
```

**Fallback if a service isn't ready.** The trace is only as complete as the services that emit spans. If `analytics` or `search` isn't ready, trace through the synchronous path (BFF → order → cart → inventory → payment) and the Kafka produce — that's the demo's core. Note in your writeup which hops are present.

---

## Step 1 — Place one order with a known idempotency key

The idempotency key lets you find this exact order again across every store.

```bash
ORDER_ID="demo-$(date +%s)"
echo "tracing order: $ORDER_ID"
BFF=$(kubectl --context kind-region-primary get svc bff-web -n shop \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

grpcurl -plaintext \
  -H "x-idempotency-key: ${ORDER_ID}" \
  -d '{"customer":"acme","sku":"SKU-42","qty":1}' \
  "${BFF}:443" order.v1.OrderService/PlaceOrder
# { "order_id": "...", "status": "PLACED" }
```

---

## Step 2 — Confirm each hop landed

Walk the order through each store, in the order it flows. This is the walk you narrate on camera.

**The cart read (CRDT, served from the local region):**

```bash
grpcurl -plaintext -d '{"customer":"acme"}' \
  cart.shop.svc.cluster.local:50051 cart.v1.CartService/GetCart
# items include SKU-42; note the region serving it
```

**The inventory reservation (the lease was acquired — single-writer-per-SKU):**

```bash
grpcurl -plaintext -d '{"sku":"SKU-42"}' \
  inventory.shop.svc.cluster.local:50051 inventory.v1.InventoryService/GetStock
# reserved: 1, lease_holder: order-service, region: us-east
```

**The payment (the Temporal workflow charged exactly once):**

```bash
temporal workflow show --workflow-id "charge-${ORDER_ID}" --namespace marketplace
# WorkflowExecutionCompleted
#   result: { charge_id: ch-..., status: charged, idempotency_key: demo-... }
```

**The event on the Kafka spine (outbox committed):**

```bash
kcat -C -b kafka:9092 -t order.placed.v1 -o -100 -e | grep "$ORDER_ID"
# {"order_id":"...","idempotency_key":"demo-...","outbox":"committed",...}
```

**The search index updated (Debezium CDC → Elasticsearch read model):**

```bash
curl -sS "http://elasticsearch:9200/orders/_doc/${ORDER_ID}" | jq '._source.status'
# "PLACED"   <-- the read model caught up via CDC
```

Each of these proves one hop. Together they prove the order flowed through the whole backbone — but the *single* artifact that proves it best is the trace.

---

## Step 3 — Pull the distributed trace

Because every service emits OpenTelemetry with propagated context, one trace ID spans every hop.

```bash
TRACE_ID=$(otel-cli trace search \
  --attr "x-idempotency-key=${ORDER_ID}" --limit 1 --format id)
echo "trace: $TRACE_ID"

otel-cli trace get --id "$TRACE_ID" --format waterfall
```

Expected waterfall (your timings will differ):

```
order.placed  ────────────────────────────────────  142ms
  bff-web.CreateOrder            ▏  8ms     mTLS=mutual
  order.PlaceOrder               ▏▏ 21ms
    cart.GetCart (CRDT read)     ▏  6ms     region=us-east
    inventory.Reserve (lease)    ▏▏ 12ms    SKU-42 lease acquired
    payment.Charge (Temporal)    ▏▏▏ 38ms   workflow=charge-demo-... idempotency=demo-...
  kafka.produce order.placed.v1  ▏  4ms     partition=3 outbox=committed
  search.Index (Debezium CDC)    ▏▏ 19ms
```

If the trace **breaks** at a hop (you see two disconnected traces instead of one), the service at that hop isn't propagating the trace context — the Week 8/17 header-propagation lesson. Fix it before the demo; a broken trace on camera undercuts the whole observability story.

---

## Step 4 — The trace-to-log jump (the move that wins the room)

From the trace, jump to the logs. In Grafana, open the trace, click the `payment.Charge` span, and follow the trace-to-logs link to Loki:

```bash
# Or from the CLI, query Loki for the logs carrying this trace ID:
logcli query "{service=\"payment\"} |= \"${TRACE_ID}\"" --limit 20
# ts ... idempotency_key=demo-... dedup_check=miss   (first time -> charge)
# ts ... db_unique_constraint=committed charge_id=ch-...
# ts ... charge confirmed for order demo-...
```

On camera you say: "Here's the payment span, 38 milliseconds. I click it, and here are the exact log lines it wrote — the idempotency check, the DB commit, the charge confirmation. One click from a span to the logs that explain it." That jump — metrics to traces to logs, correlated by trace ID — is the whole observability story of the course in one gesture.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] One order, placed with a known idempotency key, is found in the cart, inventory, payment (Temporal), Kafka, and search stores.
- [ ] A single distributed trace spans every hop (not two disconnected traces — context propagation works).
- [ ] You demonstrate the trace-to-log jump: from a span to the log lines that span emitted, correlated by trace ID.
- [ ] The waterfall shows mTLS on the meshed hops and the payment span carries the idempotency key and the Temporal workflow ID.
- [ ] You can narrate the whole walk in under three minutes (rehearse it — it's the demo's first segment).
- [ ] You can state, in one sentence, why the *trace* is better evidence than the five separate store-queries.

---

## Stretch

- Run the same trace for an order placed in the **other region** and confirm the trace shows the request served locally (no unnecessary cross-region hop on the read path).
- Induce a **slow inventory** (the Week 8 fault injection) and re-pull the trace — show the latency landing on exactly the `inventory.Reserve` span, demonstrating the trace pinpoints the slow hop.
- Record the trace-an-order walk with **asciinema** or OBS as the first draft of the demo's segment 1.

---

When this feels comfortable, move to [Exercise 2 — Region failover drill](./exercise-02-region-failover-drill.py).
