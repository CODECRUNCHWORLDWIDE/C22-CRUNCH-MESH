# Lecture 1 — Contract Testing with Pact: Closing the Polyglot Gap

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can write a consumer-driven contract with Pact, generate the pact file, verify it against a real provider with provider states, publish it to a broker, gate both pipelines with `can-i-deploy`, and articulate precisely what a contract test proves and what it does not.

If you remember one sentence from this lecture, remember this one:

> **A contract test is the consumer writing down, executably, exactly what it needs from a provider — so that the provider's CI fails the moment it stops delivering it, *before* the break reaches production.**

You have a polyglot system. The Python `order` service calls the Go `inventory` service over gRPC; both were written by people who will not be in the same standup, in languages that don't share a test runner, on release schedules that don't line up. The classic way this system breaks is depressingly ordinary: the inventory team renames a field, or tightens a type, or makes an optional field required, in a way their *own* tests still pass — because their tests don't know what `order` depends on. The break is invisible until `order` deploys against the new inventory and falls over in production. Integration tests catch *some* of this, but they're expensive, slow, and they only run when someone bothers to stand up both services together. Contract testing is the cheap, fast, always-on alternative: the consumer's expectations become an artifact the provider's pipeline is *forced* to honor.

---

## 1. Why example tests and shared schemas aren't enough

Before Pact, two things claim to solve this and don't, quite.

**Example-based unit tests** on each side test each service against *its own idea* of the other. The order service's tests mock inventory the way the order team *thinks* inventory behaves. The inventory service's tests check inventory against its own spec. Neither test knows whether those two ideas agree. The gap between "how order mocks inventory" and "how inventory actually responds" is exactly where the production break lives, and no amount of mocking inside one service closes it — because the mock is written by the same people who are wrong about the boundary.

**A shared schema** (the Protobuf `.proto`, an OpenAPI doc) is better — it's a single source of truth for the *shape*. Week 5 spent a whole week on Protobuf's compatibility rules precisely because the schema catches a class of breaks. But a schema has two limits. First, it describes *everything the provider could send*, not *what this consumer actually depends on* — a provider can make a backward-compatible-by-the-schema change (deprecate a field, change a default, alter which fields are populated in a given state) that the schema permits and a specific consumer still breaks on. Second, the schema is a passive document; nothing *fails a build* when a provider drifts from what a consumer needs, unless you wire up exactly that check — which is what contract testing *is*.

> **The distinction that makes contract testing click:** a schema says "here is the universe of valid messages." A contract says "here is the specific subset of that universe *this consumer relies on*, and here is the build that goes red if you stop delivering it." Schemas constrain the type; contracts constrain the *relationship*.

So contract testing is not a replacement for the typed Protobuf surface — it sits *on top of* it. The `.proto` gives you a compiler that rejects ill-typed messages; the contract gives you a CI gate that rejects a provider change that breaks a real, named consumer. You want both.

---

## 2. Consumer-driven contracts: the Pact model

Pact's central idea is **consumer-driven**: the *consumer* writes the contract, not the provider. This is the inversion that makes it work. The consumer knows what it actually needs — which fields, which status codes, which preconditions — because the consumer's code reads exactly those. So the consumer is the right author of the contract.

The flow has two phases and one artifact in between.

### 2.1 Phase 1 — the consumer test (against a mock provider)

In a consumer test, you spin up a Pact **mock provider** — a tiny local HTTP/gRPC server that Pact controls — and tell it: "I expect that *given* inventory has SKU-42 in stock, *when* I send a `CheckStock(SKU-42)` request, *then* I get back `{available: true, quantity: 7}`." Then you run your *real consumer client code* against that mock. Two things happen:

1. Your consumer code is exercised against a response shaped exactly as you declared — so you've tested that your client *parses and uses* that response correctly.
2. Pact records the interaction (the expected request and the response you declared) into a **pact file** — a JSON document that is now the contract.

Here is a Pact consumer test for `order` (Python) calling `inventory`, written against the REST-style surface Pact handles most directly (the gRPC plugin handles the Protobuf case; the shape of the test is identical):

```python
# test_order_inventory_contract.py  — the CONSUMER test (order's repo)
import atexit
import pytest
from pact import Consumer, Provider

# The mock provider Pact stands up. order's client will hit this, not real inventory.
pact = Consumer("order-service").has_pact_with(
    Provider("inventory-service"),
    host_name="127.0.0.1", port=1234,
    pact_dir="./pacts",
)
pact.start_service()
atexit.register(pact.stop_service)


def test_check_stock_available():
    expected = {"sku": "SKU-42", "available": True, "quantity": 7}

    (pact
     .given("inventory has 7 of SKU-42 in stock")   # the PROVIDER STATE (see §3)
     .upon_receiving("a stock check for SKU-42")
     .with_request("GET", "/v1/stock/SKU-42")
     .will_respond_with(200, body=expected))

    with pact:
        # This is order's REAL client code, exercised against the mock.
        result = inventory_client.check_stock("SKU-42")
        assert result.available is True
        assert result.quantity == 7
```

When this test passes, two artifacts exist: a green test (order parses the response correctly) and `./pacts/order-service-inventory-service.json` — the pact file. That file *is* the contract. It says, in machine-readable form, "order-service requires that inventory-service, given 7 of SKU-42 in stock, responds to `GET /v1/stock/SKU-42` with `{sku, available, quantity}`."

### 2.2 The pact file: the artifact in the middle

The pact file is the whole point. It's a normal JSON document — you can read it, diff it, check it into git, and (the important part) hand it to the *provider's* pipeline. A trimmed version of the one the test above produces:

```json
{
  "consumer": { "name": "order-service" },
  "provider": { "name": "inventory-service" },
  "interactions": [
    {
      "description": "a stock check for SKU-42",
      "providerState": "inventory has 7 of SKU-42 in stock",
      "request":  { "method": "GET", "path": "/v1/stock/SKU-42" },
      "response": {
        "status": 200,
        "body": { "sku": "SKU-42", "available": true, "quantity": 7 }
      }
    }
  ],
  "metadata": { "pactSpecification": { "version": "3.0.0" } }
}
```

Notice what it does *not* contain: any of order's code, any of inventory's code. It's a pure description of the agreed interaction. That language-neutrality is why Pact works across a polyglot system — the Python consumer produces a JSON file the Go provider can verify, because neither side needs to read the other's source.

### 2.3 Phase 2 — provider verification (against the real provider)

Now the provider's pipeline takes the pact file and *replays it against the real inventory service*. For each interaction, Pact: sets up the named provider state, sends the recorded request to the actual running provider, and checks the actual response against the recorded expectation. If inventory still responds with `{sku, available, quantity}` for an in-stock SKU, verification passes. If the inventory team renamed `quantity` to `qty`, verification *fails* — in inventory's own CI, the moment they make the change, with a message that names order-service as the consumer they're about to break.

Here's provider verification in Go (`pact-go`), run in inventory's repo:

```go
// inventory_provider_test.go — the PROVIDER verification (inventory's repo)
func TestInventoryProvider(t *testing.T) {
    verifier := provider.NewVerifier()

    err := verifier.VerifyProvider(t, provider.VerifyRequest{
        ProviderBaseURL: "http://127.0.0.1:8080", // the REAL inventory, running
        Provider:        "inventory-service",

        // Pull the consumer's pact from the broker (see §4):
        BrokerURL:      os.Getenv("PACT_BROKER_URL"),
        PublishVerificationResults: true,
        ProviderVersion: os.Getenv("GIT_SHA"),

        // Provider-state handlers: set up the precondition each interaction names.
        StateHandlers: map[string]models.StateHandler{
            "inventory has 7 of SKU-42 in stock": func(setup bool, s models.ProviderState) (models.ProviderStateResponse, error) {
                // seed the DB / fixture so a real GET /v1/stock/SKU-42 returns 7
                seedStock("SKU-42", 7)
                return nil, nil
            },
        },
    })
    if err != nil {
        t.Fatal(err) // inventory CHANGED in a way that breaks order — fail here, not in prod
    }
}
```

The asymmetry is the magic: **the consumer never runs the provider's code and the provider never runs the consumer's code.** The pact file is the only thing that crosses the boundary, and it crosses it as data. That's what lets a Python team and a Go team enforce a contract without sharing a test harness.

---

## 3. Provider states: making verification deterministic

The one part of Pact that trips people up is **provider states**, so spend a minute on it. An interaction often depends on a precondition: "given SKU-42 is in stock" produces a different response than "given SKU-42 is out of stock." The consumer declares the precondition by name (`given("inventory has 7 of SKU-42 in stock")`), and the provider supplies a **state handler** that *makes that precondition true* before the interaction is verified — seeds the database, sets a fixture, whatever it takes for a real request to produce the expected response.

This matters for two reasons:

- **It keeps verification deterministic.** Without provider states, verification would depend on whatever happens to be in the provider's database, which is flaky. With them, each interaction sets up exactly the world it assumes.
- **It documents the consumer's assumptions about the provider's *state*, not just its *shape*.** "Given out of stock, I expect `available: false`" is a real contract clause — and it forces the provider to handle that state correctly, which is a class of bug (the empty-state response) that shape-only checks miss.

The discipline: **every interaction that depends on data should name a provider state, and the provider must implement a handler for every state name its consumers use.** A pact that references a provider state the provider doesn't handle fails verification with "no state handler for X" — which is Pact telling you the two sides disagree about a precondition, which is itself a real find.

---

## 4. The Pact Broker: from a file to a pipeline gate

A pact file checked into git is better than nothing, but the production-grade setup runs a **Pact Broker** — a server that stores pacts and verification results and, crucially, answers the one question that turns contract testing from documentation into a gate: **`can-i-deploy`**.

### 4.1 What the broker stores

The broker holds, for every consumer-provider pair:

- The **pacts** the consumer published (tagged by branch and version).
- The **verification results** the provider published (did inventory v-abc123 verify order's pact? pass/fail).
- The **deployment state**: which version of each service is currently deployed to each environment (`production`, `staging`).

From these three facts it can answer questions no single pipeline can answer alone, because the answer depends on what's deployed *across* services.

### 4.2 `can-i-deploy`: the gate that blocks the break

`can-i-deploy` is the command that makes contract testing matter. Before you deploy a version of a service, you ask the broker:

```bash
# Before deploying inventory v-abc123 to production, ask:
# "will this break any consumer already live in production?"
pact-broker can-i-deploy \
  --pacticipant inventory-service --version abc123 \
  --to-environment production \
  --broker-base-url "$PACT_BROKER_URL"
```

The broker looks at every consumer currently deployed to production (order-service, search-service, the BFFs), finds the pacts they published, and checks whether inventory v-abc123 has a *passing verification* against each of those pacts. If yes — every live consumer's contract still holds against this version — it returns success and the deploy proceeds. If inventory v-abc123 fails order-service's pact, `can-i-deploy` returns **non-zero**, and the deploy is **blocked**:

```
Computer says no ¯\_(ツ)_/¯

The following pacts have not been successfully verified by inventory-service:
  order-service (production) -> inventory-service abc123  FAILED

inventory-service abc123 cannot be deployed to production because it would
break order-service, which is currently deployed there.
```

*That* is the difference between contract testing that works and contract testing that decorates a wiki. The pact isn't a document someone reads; it's a check in the pipeline that physically refuses to ship a provider that would break a live consumer. The whole apparatus — consumer test, pact file, broker, provider verification, `can-i-deploy` — exists to produce that one non-zero exit code at the right moment.

### 4.3 The deploy/release dance

The full lifecycle, so the moving parts click together:

1. **Consumer CI:** order's tests run, produce the pact, **publish** it to the broker tagged with order's branch and version.
2. **Provider CI:** inventory's tests run, **pull** the relevant pacts from the broker, verify them against real inventory, and **publish** the results.
3. **Before any deploy:** the deploying service runs `can-i-deploy --to-environment <env>`; the broker says yes or no based on the cross-service verification matrix.
4. **After a successful deploy:** the service **records the deployment** (`pact-broker record-deployment`) so the broker knows what's live where — which is the input to the *next* `can-i-deploy`.

Step 4 is the one people forget, and without it `can-i-deploy` can't reason about what's actually in production. The broker's answer is only as good as its knowledge of what's deployed.

### 4.4 The matrix the broker actually computes

It helps to picture the broker's state as a matrix: rows are consumer versions, columns are provider versions, and each cell is "did this provider version verify this consumer's pact — pass, fail, or unknown." `can-i-deploy` is a query over that matrix combined with the deployment table. When you ask "can I deploy inventory v-abc123 to production," the broker:

1. Looks up every consumer currently *deployed to production* (from the deployment table): order-service v-9, search-service v-4, bff-web v-2.
2. For each, finds the pact that consumer published.
3. Checks the matrix cell: did inventory v-abc123 verify that pact?
4. Returns success only if *every* cell is a pass. Any fail or unknown is a block.

The "unknown" case is the subtle one and worth internalizing: if inventory v-abc123 has simply *never been verified* against order's pact (maybe verification hasn't run yet), `can-i-deploy` returns a block, not a pass — because "we don't know it's safe" is correctly treated as "not safe to deploy." This fail-closed default is what makes the gate trustworthy: it never lets a deploy through on the absence of evidence, only on the presence of a passing verification. A gate that defaulted to "allow unless proven broken" would let an unverified provider ship, which is exactly the gap you adopted contract testing to close.

### 4.5 Pending pacts and WIP: not blocking the provider on a brand-new consumer

A practical wrinkle that trips up real adoptions: when a *new* consumer publishes its first pact, the provider's verification suddenly has a new pact to satisfy — and if the provider doesn't satisfy it yet (the new consumer asked for something not built), the provider's build goes red *for a change the provider didn't make*. That's a terrible incentive: it makes provider teams resent contract testing. Pact's answer is **pending pacts** and **WIP (work-in-progress) pacts**: a brand-new consumer's pact is marked pending, so a provider failing it produces a *warning, not a build failure*, until the provider has verified it once. This lets a consumer publish an expectation the provider hasn't met yet without breaking the provider's pipeline — the contract becomes binding only once both sides have agreed to it (the provider verified it at least once). It's the mechanism that lets contract testing be adopted *incrementally* across a large org without the first new consumer breaking every provider build. Know it exists; you'll need it the day a new service joins your capstone's broker.

---

## 5. Contract testing over gRPC and the Kafka spine

Your capstone isn't REST — it's gRPC and Kafka. Pact handles both, with two extensions worth knowing.

**gRPC / Protobuf.** The `pact-protobuf-plugin` lets you write the same consumer-driven contract over a Protobuf message and a gRPC method instead of an HTTP path and a JSON body. The consumer declares "given this state, when I call `inventory.v1.InventoryService/CheckStock` with this request message, I expect this response message," and verification replays the gRPC call against the real provider. The *model* is identical — consumer declares, provider verifies, broker gates — only the transport and the matching (on Protobuf fields instead of JSON keys) differ. This is the mode you'll actually use for the capstone's synchronous boundaries (order → inventory, order → payment).

**Message pacts (Kafka).** The asynchronous boundary — `order.placed.v1` flowing over Kafka from order to search — is a *message pact*. There's no request/response; instead the consumer (search) declares "I expect to receive a message shaped like this, and here's the handler that processes it," and the provider (order) verifies that the message it *produces* matches. This catches the event-schema break: the day order adds a required field to `order.placed.v1` that search's consumer chokes on. Message pacts are how you extend contract testing across the event spine, not just the gRPC calls — and the capstone's Kafka backbone is exactly where an un-contracted event schema drifts silently until a consumer breaks.

> **The unifying idea across REST, gRPC, and messages:** a contract is always "consumer declares the shape and the preconditions it depends on; provider proves it still delivers them." The transport changes; the discipline doesn't. Wherever two services meet — a gRPC call, an HTTP route, a Kafka topic — there's a boundary a contract can lock.

---

## 5b. Contracting the error paths, not just the happy path

A contract that only covers the success response is half a contract. The interactions that catch the *nastiest* production breaks are the error and edge states, because those are the ones the provider is most likely to change without thinking about consumers. Three states every boundary should contract:

- **The empty/not-found state.** "Given SKU-99 does not exist, when I check stock, then I get a 404 (or a gRPC `NOT_FOUND`)." This forces the provider to keep handling the missing-entity case the way the consumer expects — and it forces the *consumer* test to prove it handles a 404 without crashing. The day the provider changes a not-found from a 404 to a 200-with-empty-body, this interaction goes red and you've caught a break that would otherwise surface as the consumer mis-parsing an unexpected success.
- **The validation-error state.** "Given a malformed request, then I get a 400 with this error shape." Consumers branch on error shapes; if the provider changes the error envelope, the consumer's error handling silently breaks. Contracting it locks the error contract too.
- **The degraded/partial state.** For the capstone: "given inventory is in a read-only degraded mode, then stock checks return a `stale: true` flag." If your services have degraded modes (Week 7's graceful degradation), the *shape* of the degraded response is part of the contract the consumer depends on.

The discipline: **for every boundary, contract at least one success, one not-found/empty, and one error interaction.** A pact suite that's all happy-path is testing the case least likely to break and ignoring the cases most likely to. The Problem-1 homework asks for at least two interactions per boundary for exactly this reason — and the strongest answers contract the error path, because that's where the consumer's resilience and the provider's drift actually meet.

There's a subtle reason the error path matters even more in a *resilient* system: your Week 7/8 work made consumers degrade gracefully when a dependency fails — which means the consumer has *code that runs on the error response*, and that code is only as correct as its assumption about the error's shape. A consumer that catches a 503 and serves a cached fallback is depending on getting a 503, not a 500 or a silent 200-with-empty-body. Contract the error and you've locked the input to the degradation logic; leave it un-contracted and the day the provider changes its failure shape, your *graceful degradation* is the thing that breaks — the cruelest failure mode, because the resilience feature itself fails. The error contract is what keeps your resilience resilient.

## 6. What contract testing does NOT catch (the honest boundary)

This is the section that separates someone who *uses* Pact from someone who *understands* it. Contract testing is powerful and it is narrow, and conflating the two is how teams get a false sense of safety.

A pact proves: **the agreed interactions have the agreed shape, and the named preconditions produce the named responses.** That's it. It does *not* prove:

- **Business correctness.** A pact says "given in stock, inventory returns `available: true`." It does *not* say inventory's stock-counting logic is *correct* — that the number 7 is the *right* number. If inventory has a bug that returns 7 when the true count is 5, the pact passes (the shape is right) and the system is wrong. Semantics live below the contract.
- **Every input.** A pact verifies the *specific interactions the consumer wrote down* — typically a handful. It says nothing about the inputs nobody declared. The exhaustive-input question is what property-based testing (Lecture 2) answers; contract testing answers the *boundary-shape* question. They're complements, not substitutes.
- **The provider's behavior in states no consumer declared.** If no consumer ever wrote a "given out of stock" interaction, the pact never checks the out-of-stock path. Contract coverage is exactly the union of what consumers asked for — no more.
- **Non-functional properties.** Latency, throughput, ordering guarantees, idempotency under retry — none of these are in a pact. The capacity model (Lecture 2) and the chaos drills (Week 22) cover those.

The challenge this week (`challenge-01`) is built entirely on this boundary: a pact suite that's *green* while production is *broken*, because the break is a semantic one the shape-matching contract can't see. The lesson you'll carry out of it is the one to internalize now: **a green pact means "the shape is right and the agreed interactions hold," and you must not let it mean "the system is correct."** Contract testing closes the polyglot *boundary-shape* gap, which is a real and common source of outages — and it leaves the semantic gap and the input-space gap for other tools. Knowing exactly which gap each tool closes is the literacy this week builds.

---

## 7. Where contract testing fits in the capstone

Concretely, for the Polyglot Marketplace Backbone:

- **The required deliverable** is "a published Pact broker URL with green contracts." That's not decoration — it's the evidence that your polyglot boundaries are locked. A reviewer who sees a green broker knows that order can't be silently broken by an inventory change, because the broker would have blocked it.
- **The boundaries to contract** are the ones the syllabus names: `cart ↔ inventory`, `cart ↔ payment`, and (via message pacts) `order → search` over `order.placed.v1`. These are the polyglot seams — Rust/Go, Python/Go, Python/Python-over-Kafka — exactly where a shared test harness *can't* reach and a contract can.
- **The pipeline gate** is `can-i-deploy`, run in-cluster against the in-cluster broker, so a capstone deploy that would break a live consumer is refused. Demonstrating that refusal — deliberately breaking a provider and watching `can-i-deploy` block it — is the single most convincing thing you can show a reviewer about your boundary discipline.

The mini-project this week stands up exactly this: the broker in-cluster, pacts for the named boundaries, and a demonstrated `can-i-deploy` block. Build it now, because next week it's a capstone artifact you defend, not one you write.

---

## 7b. Contract testing vs a schema registry: not the same tool

A question that always comes up: "we use a Confluent Schema Registry for our Kafka topics — isn't that contract testing?" No, and the distinction is worth getting exactly right because the two are complementary and people conflate them.

A **schema registry** enforces, at produce/consume time, that messages conform to a registered schema and that schema *evolution* follows compatibility rules (a new schema version must be backward- or forward-compatible with the old, per the registry's configured policy). That's real and valuable — it's the Protobuf compatibility discipline from Week 5, enforced at runtime by infrastructure. But notice what it constrains: the *schema*, the universe of valid messages. It does not know which *fields a specific consumer reads*, and it does not *block a deploy* — it rejects a non-conforming message at runtime, which is later and more disruptive than failing a build.

A **contract test** constrains the *relationship*: this specific consumer depends on these specific fields under these specific conditions, and the provider's CI fails if it stops delivering them. It runs at build time, per service, and gates the deploy. The two tools answer different questions:

| | Schema registry | Contract test (Pact) |
|---|---|---|
| **Constrains** | The schema (valid-message universe) | The relationship (what *this* consumer needs) |
| **When** | Runtime (produce/consume) | Build time (CI) |
| **Enforcement** | Rejects a bad message | Blocks a breaking deploy |
| **Knows consumer field usage?** | No | Yes |
| **Catches** | Schema-incompatible evolution | A compatible-by-schema change that breaks a real consumer |

The honest position: use both. The schema registry (or the Protobuf compiler) gives you the type floor; the contract test gives you the relationship gate. A change can pass the schema's compatibility check (it's backward-compatible) and still break a consumer (it stopped populating a field that consumer relied on) — and *only* the contract test catches that. For the capstone's Kafka spine, the schema registry validates `order.placed.v1`'s evolution and the message pact validates that order keeps delivering what search reads. Neither replaces the other.

---

## 8. Recap

You should now be able to:

- Explain why example tests and shared schemas leave a boundary-shape gap, and how a consumer-driven contract closes it by making the consumer's needs an artifact the provider's CI must honor.
- Write a Pact consumer test against the mock provider, understand the pact file as the language-neutral artifact in the middle, and verify it against the real provider with provider-state handlers.
- Run a Pact Broker, publish pacts and verification results, and use `can-i-deploy` as the gate that *blocks* a deploy that would break a live consumer.
- Extend contract testing across gRPC (the Protobuf plugin) and Kafka (message pacts), and state the unifying "consumer declares, provider verifies, broker gates" model.
- State precisely what a contract test proves (shape + named interactions + preconditions) and what it does not (business correctness, exhaustive inputs, non-functional properties) — and why that makes property testing and capacity planning its necessary complements.
- Contract the error and degraded paths, not just the happy path, because that's where provider drift and consumer resilience meet — and avoid the three adoption mistakes (the decorative pact that doesn't gate, the over-specified pact that cries wolf, the provider-authored pact that isn't consumer-driven).
- Place contract testing correctly against a schema registry: the registry constrains the message *universe* at runtime; the contract constrains the *relationship* at build time and blocks the deploy. Use both — neither replaces the other.

### The three adoption mistakes to avoid

Before you move on, the recurring ways teams get contract testing *wrong*, so you don't:

- **The decorative pact.** Pacts that get published but never gate a deploy — `can-i-deploy` isn't in the pipeline, so a breaking change ships and the green broker was theater. The fix is wiring `can-i-deploy` as a *required* status check, so the gate physically blocks. A pact that doesn't gate is documentation, not a test.
- **The over-specified pact.** A pact that asserts on *every* field of a response, including ones the consumer doesn't use, makes the provider's build red on changes that don't affect the consumer at all — which trains the provider team to ignore or disable contract tests. Specify only what the consumer *reads*. Pact's matchers (`like`, `eachLike`, type matchers) let you assert "a field of this type exists" rather than an exact value, which is usually what you actually depend on.
- **The provider-authored pact.** If the provider writes the pact, it's not consumer-driven — it's the provider asserting its own behavior, which proves nothing about what consumers need. The consumer must author it. A provider-written "contract" is just the provider's tests wearing a Pact costume.

Avoid those three and contract testing does what it promises: makes a polyglot boundary impossible to break silently. Fall into them and you get a green broker that lies, which is worse than no broker.

Next up: the tests that hunt the inputs you'd never write by hand, the CRDT-merge laws, and the queueing math that sizes a service before you ship it. Continue to [Lecture 2 — Property-Based Testing and Capacity Planning](./02-property-based-testing-and-capacity-planning.md).

---

## References

- *Pact — How Pact works*: <https://docs.pact.io/getting_started/how_pact_works>
- *Pact — Verifying pacts*: <https://docs.pact.io/getting_started/verifying_pacts>
- *Pact — Provider states*: <https://docs.pact.io/getting_started/provider_states>
- *Pact — The Pact Broker*: <https://docs.pact.io/pact_broker>
- *Pact — `can-i-deploy`*: <https://docs.pact.io/pact_broker/can_i_deploy>
- *pact-python*: <https://github.com/pact-foundation/pact-python>
- *pact-go*: <https://github.com/pact-foundation/pact-go>
- *Pact — Protobuf/gRPC plugin*: <https://github.com/pactflow/pact-protobuf-plugin>
- *Pact — bi-directional contract testing*: <https://docs.pact.io/bi-directional_contract_testing>
