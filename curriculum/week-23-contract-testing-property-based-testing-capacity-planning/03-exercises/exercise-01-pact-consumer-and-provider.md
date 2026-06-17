# Exercise 1 — Pact Consumer and Provider Verification (Across the Polyglot)

**Goal:** Write a consumer-driven contract for the **Python `order`** service calling the **Go `inventory`** service, generate the pact file, verify it against the *real* provider with a provider state, publish it to a local **Pact Broker**, and run **`can-i-deploy`**. Then deliberately break the provider and watch `can-i-deploy` *refuse* the deploy — the moment that makes contract testing real. You will train the single most important contract-testing habit: making the consumer's needs an artifact the provider's CI is forced to honor.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need Docker (for the broker), a Python toolchain with `pact-python`, and a Go toolchain with `pact-go`.

```bash
python3 --version          # 3.11+
go version                 # 1.22+
docker --version           # for the broker
pip install pact-python
```

**Fallback if your real services aren't ready.** The consumer side uses a tiny `order` client; the provider side can be a 30-line Go HTTP stub standing in for `inventory`. Both are given below. The contract flow is byte-for-byte identical whether the provider is your real service or the stub — which is itself a lesson: the pact doesn't care about the provider's internals, only its responses.

---

## Step 1 — Stand up the Pact Broker

```bash
docker run -d --name pact-broker -p 9292:9292 \
  -e PACT_BROKER_DATABASE_URL="sqlite:////tmp/pact_broker.sqlite" \
  pactfoundation/pact-broker:latest

export PACT_BROKER_URL="http://localhost:9292"
curl -sS "$PACT_BROKER_URL" >/dev/null && echo "broker up"
```

The broker UI is at <http://localhost:9292> — open it; it's empty now, and by the end of this exercise it will show one consumer, one provider, one pact, and one green verification.

---

## Step 2 — Write the consumer test (order, Python)

The consumer declares what it needs from inventory. Save as `test_order_inventory_contract.py`:

```python
import atexit
import requests
from pact import Consumer, Provider

PACT_MOCK_PORT = 1234
pact = Consumer("order-service").has_pact_with(
    Provider("inventory-service"),
    host_name="127.0.0.1", port=PACT_MOCK_PORT,
    pact_dir="./pacts",
)
pact.start_service()
atexit.register(pact.stop_service)


def check_stock(sku: str):
    """order's REAL client code — this is what we're contracting."""
    r = requests.get(f"http://127.0.0.1:{PACT_MOCK_PORT}/v1/stock/{sku}", timeout=2)
    r.raise_for_status()
    return r.json()


def test_check_stock_in_stock():
    expected = {"sku": "SKU-42", "available": True, "quantity": 7}
    (pact
     .given("inventory has 7 of SKU-42 in stock")     # PROVIDER STATE
     .upon_receiving("a stock check for SKU-42")
     .with_request("GET", "/v1/stock/SKU-42")
     .will_respond_with(200, body=expected))

    with pact:
        result = check_stock("SKU-42")
        assert result["available"] is True
        assert result["quantity"] == 7


def test_check_stock_out_of_stock():
    expected = {"sku": "SKU-99", "available": False, "quantity": 0}
    (pact
     .given("inventory has 0 of SKU-99 in stock")     # a SECOND provider state
     .upon_receiving("a stock check for an out-of-stock SKU")
     .with_request("GET", "/v1/stock/SKU-99")
     .will_respond_with(200, body=expected))

    with pact:
        result = check_stock("SKU-99")
        assert result["available"] is False
```

Run it:

```bash
pytest test_order_inventory_contract.py -q
# 2 passed
ls pacts/
# order-service-inventory-service.json   <-- the CONTRACT, generated
```

Open the pact file. It's pure JSON — no Python, no Go — describing two interactions with their provider states. That language-neutrality is why the Go provider can verify it.

---

## Step 3 — Publish the pact to the broker

```bash
pact-broker publish ./pacts \
  --consumer-app-version "$(git rev-parse --short HEAD 2>/dev/null || echo dev-1)" \
  --branch main \
  --broker-base-url "$PACT_BROKER_URL"
# Pact published. Check the broker UI — order-service -> inventory-service now exists.
```

---

## Step 4 — The provider (Go) and its verification

The real `inventory` is your provider. If it's not ready, here's the stub — save as `inventory_stub.go` and run it on :8080:

```go
package main

import (
	"encoding/json"
	"net/http"
	"strings"
	"sync"
)

var (
	mu    sync.Mutex
	stock = map[string]int{} // seeded by the provider-state setup endpoint
)

type stockResp struct {
	SKU       string `json:"sku"`
	Available bool   `json:"available"`
	Quantity  int    `json:"quantity"`
}

func main() {
	// The real stock endpoint the pact verifies against.
	http.HandleFunc("/v1/stock/", func(w http.ResponseWriter, r *http.Request) {
		sku := strings.TrimPrefix(r.URL.Path, "/v1/stock/")
		mu.Lock()
		q := stock[sku]
		mu.Unlock()
		json.NewEncoder(w).Encode(stockResp{SKU: sku, Available: q > 0, Quantity: q})
	})

	// Provider-state setup: pact-go POSTs here before each interaction to make the
	// named precondition true. This is how "given 7 of SKU-42 in stock" becomes real.
	http.HandleFunc("/_pact/provider_states", func(w http.ResponseWriter, r *http.Request) {
		var body struct{ State string `json:"state"` }
		json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		defer mu.Unlock()
		switch body.State {
		case "inventory has 7 of SKU-42 in stock":
			stock = map[string]int{"SKU-42": 7}
		case "inventory has 0 of SKU-99 in stock":
			stock = map[string]int{"SKU-99": 0}
		}
		w.WriteHeader(http.StatusOK)
	})

	http.ListenAndServe(":8080", nil)
}
```

```bash
go run inventory_stub.go &      # provider listening on :8080
```

Now verify the pact against it (`pact-go` verifier, save as `verify_test.go` or run the CLI):

```bash
# Using the pact CLI verifier against the running provider:
pact-provider-verifier \
  --provider-base-url http://127.0.0.1:8080 \
  --provider inventory-service \
  --provider-states-setup-url http://127.0.0.1:8080/_pact/provider_states \
  --pact-broker-base-url "$PACT_BROKER_URL" \
  --consumer-version-selectors '{"branch":"main"}' \
  --publish-verification-results \
  --provider-app-version "$(git rev-parse --short HEAD 2>/dev/null || echo prov-1)"
# Verifying a pact between order-service and inventory-service
#   Given inventory has 7 of SKU-42 in stock
#     a stock check for SKU-42 ... OK
#   Given inventory has 0 of SKU-99 in stock
#     a stock check for an out-of-stock SKU ... OK
# 2 interactions, 0 failures
```

Green verification, published back to the broker. The UI now shows the pact *verified* by inventory-service.

---

## Step 5 — `can-i-deploy`: the gate

Record that both are "deployed" to an environment, then ask the gate:

```bash
pact-broker record-deployment --pacticipant order-service \
  --version "$(git rev-parse --short HEAD 2>/dev/null || echo dev-1)" \
  --environment production --broker-base-url "$PACT_BROKER_URL"

pact-broker can-i-deploy \
  --pacticipant inventory-service \
  --version "$(git rev-parse --short HEAD 2>/dev/null || echo prov-1)" \
  --to-environment production \
  --broker-base-url "$PACT_BROKER_URL"
# Computer says yes \o/  — inventory can deploy; order's contract still holds.
```

---

## Step 6 — Break the provider, watch the gate block

Now the payoff. Change the stub to rename `quantity` → `qty` (a backward-incompatible change to order's contract):

```go
// In stockResp, change the JSON tag — this BREAKS order's contract:
Quantity int `json:"qty"`   // was "quantity"
```

Re-run the provider, re-verify, and re-ask `can-i-deploy`:

```bash
go run inventory_stub.go &
pact-provider-verifier ... --provider-app-version prov-2   # (same flags as Step 4)
# a stock check for SKU-42 ... FAILED
#   expected key 'quantity' but it was missing (found 'qty')
# 2 interactions, 1 failure

pact-broker can-i-deploy --pacticipant inventory-service --version prov-2 \
  --to-environment production --broker-base-url "$PACT_BROKER_URL"
# Computer says no ¯\_(ツ)_/¯
#   order-service (production) -> inventory-service prov-2  FAILED
#   inventory-service prov-2 cannot be deployed to production because it would
#   break order-service.
# exit code: 1
```

**That non-zero exit is the whole point of contract testing.** A provider change that would have broken order-service in production is refused at the gate, in inventory's own pipeline, naming the consumer it would break — before a single user sees it.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] The consumer test passes and generates `pacts/order-service-inventory-service.json` with two interactions and their provider states.
- [ ] The pact is published to the broker and visible in the UI.
- [ ] Provider verification passes (2 interactions, 0 failures) and publishes results back to the broker.
- [ ] `can-i-deploy` returns success ("yes") for the compatible provider version.
- [ ] After the `quantity`→`qty` break, provider verification **fails** and `can-i-deploy` returns **non-zero** ("no"), naming order-service as the consumer that would break.
- [ ] You can state, in one sentence, why the consumer (not the provider) authors the contract.

---

## Stretch

- Switch the boundary to **gRPC/Protobuf** with the `pact-protobuf-plugin`: contract `order` → `inventory` over the real `inventory.v1.InventoryService/CheckStock` method instead of a REST path. The flow is identical; the matching is on Protobuf fields.
- Add a **message pact** for `order.placed.v1` over Kafka: `order` is the producer, `search` the consumer. Verify that the message order *produces* matches what search *expects* — the event-spine contract.
- Wire `can-i-deploy` into a **GitHub Actions** matrix across the two languages and demonstrate it failing a CI run on the breaking change. The CI block is the production-grade version of the manual block you just did.

---

When this feels comfortable, move to [Exercise 2 — Property tests for the CRDT merge](./exercise-02-property-tests-crdt-merge.py).
