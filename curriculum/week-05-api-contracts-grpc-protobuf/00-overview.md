# Week 5 — API Contracts: gRPC, Protobuf, and the Typed Surface

Welcome to the week where the boundary you scaffolded last week stops being a polite suggestion and becomes a *contract* — a typed, versioned, machine-checked surface that two services in two different languages must both honor or the build fails. By Friday you will define a Protobuf schema, generate Go and Python code from it, run a Go server and a Python client that talk to each other with zero hand-written serialization, add streaming, wire reflection, and — most importantly — be able to evolve that schema without breaking the clients already in production.

Last week's `cart`→`catalog` boundary was HTTP+JSON: untyped, unversioned, and held together by hope and a shared README. That's fine for a prototype and a liability in production. JSON over HTTP has no schema the compiler enforces; a typo in a field name is a runtime 500 at 3 a.m., not a build error at your desk. A field that `catalog` renamed last sprint silently becomes `null` in `cart`, and nobody notices until a customer sees a $0.00 price. This week replaces hope with a contract.

The one thing to internalize before you read another line: **a typed contract is a moral position, not just an engineering convenience.** When you publish a Protobuf schema, you are making a *promise* to every consumer — current and future — about the shape of your data and the rules under which it may change. The Protobuf wire format and its schema-evolution rules exist to let you keep that promise: add fields without breaking old clients, deprecate fields without deleting them, and never, ever reuse a field number. REST with hand-rolled JSON makes the same promise impossible to keep, because nothing stops you from breaking it and nothing tells the consumer you did. The typed surface is how a polyglot system of dozens of services stays coherent. It is the single most leveraged decision in the whole platform.

This week is where your boundaries grow a spine.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the Protobuf wire format at the byte level — tags (field number + wire type), varints, length-delimited fields — and why this encoding makes additive schema changes backward- and forward-compatible.
- **Author** a `.proto` v3 schema for a real service (`catalog.v1`) using the Protobuf style guide: correct package and versioning, `message` and `service` definitions, well-known types, and field-numbering discipline.
- **State and apply** the schema-evolution rules — what you may add, what you must never do (reuse a field number, change a field's type, renumber), and how `reserved` protects you from a deleted field's number being recycled.
- **Generate** Go and Python stubs from one schema with `protoc` / `buf`, and explain the difference between static (generated) stubs and reflective invocation.
- **Build** a gRPC server in Go and a gRPC client in Python that interoperate over the same contract, with no hand-written serialization on either side — proving the contract is the only thing they share.
- **Implement** all four gRPC RPC kinds — unary, server-streaming, client-streaming, and bidirectional-streaming — and state when each is the right tool.
- **Wire** a gRPC interceptor (the gRPC equivalent of middleware) for cross-cutting concerns, enable server reflection, and exercise a running service with `grpcurl` without any generated client at all.
- **Choose** between REST, gRPC, GraphQL (and Federation), and AsyncAPI/events for a given boundary, with evidence — and defend the choice the way you'd defend it in a design review.

## Prerequisites

This week assumes you have completed **C22 weeks 1–4**, or have equivalent distributed-systems fluency. Specifically:

- You finished the **Week 4 mini-project** (`marketplace-seam`) and have a `cart` (Go) and `catalog` (Python) talking over HTTP+JSON. This week replaces that HTTP boundary with a typed gRPC contract, so having it built makes everything concrete. If you skipped it, the standalone services in the exercises are your fallback.
- You understand from Week 4 *why* the boundary must survive being polyglot — that a contract held together by a shared Go struct is not a contract. gRPC + Protobuf is the mechanism that makes the boundary honest across languages.
- You can write and run a basic Go program (modules, structs, goroutines, `context.Context`) and a basic Python service (a `venv`, `pip`, async or threaded handlers). We use both; we don't teach either.
- You have `protoc` or `buf` installable (the exercises walk the install), plus the Go and Python gRPC plugins. `protoc --version` should be runnable by the end of Monday.
- You recall the Week 1 layering instinct — that an abstraction (HTTP/2 here) sits under your API and its behavior leaks through. gRPC's HTTP/2 substrate is exactly such a layer, and its multiplexing and streaming are *why* gRPC can do things REST-over-HTTP/1.1 cannot.

You do **not** need prior gRPC or Protobuf experience. We start at the wire format and build to bidirectional streaming and reflection. If you've used gRPC only through a generated client without knowing what a field number *is* or why you can't reuse one, this is the week that knowledge becomes load-bearing.

## Topics covered

- **The Protobuf wire format.** Tag-length-value encoding: the field tag (`field_number << 3 | wire_type`), varint encoding of integers, length-delimited encoding of strings/bytes/messages, and zig-zag for signed types. *Why* this encoding is the reason additive changes don't break old readers (unknown fields are skipped, not rejected).
- **proto3 schema authoring.** `syntax = "proto3"`, package naming and the `v1`/`v2` versioning convention, `message`, `service`, `rpc`, scalar and well-known types (`google.protobuf.Timestamp`, `Money`-style patterns), `repeated`, `map`, `oneof`, and `enum` with the mandatory zero value.
- **Schema evolution — the rules that keep the promise.** What's safe (add a field with a new number; add an `enum` value; add an `rpc`). What's forbidden (reuse or change a field number; change a field's type; rename in a way that changes the wire — for proto3, names don't matter on the wire, numbers do). The `reserved` keyword for retiring field numbers and names so they can never be recycled. Backward vs forward compatibility, defined precisely.
- **gRPC's four RPC kinds.** Unary (request → response); server-streaming (request → stream of responses, e.g. a product feed); client-streaming (stream of requests → response, e.g. bulk upload); bidirectional-streaming (two independent streams, e.g. a live chat or a price ticker). When each is correct and the failure modes of each.
- **gRPC's HTTP/2 substrate.** Why gRPC needs HTTP/2 (multiplexed streams, header compression, binary framing), what that buys you (true streaming, one connection for many concurrent calls), and gRPC-Web / Connect for browser clients that can't speak raw HTTP/2 trailers.
- **Static stubs vs reflection.** Generated (static) client/server code is the normal path; server reflection lets tools like `grpcurl` call a service with no generated client, by asking the server for its own schema at runtime. Interceptors as the cross-cutting-concern hook (logging, auth, tracing — you'll add real tracing in Week 6).
- **Polyglot codegen.** One `.proto`, Go stubs (`protoc-gen-go`, `protoc-gen-go-grpc`) and Python stubs (`grpcio-tools`), and the demonstration that a Go server and a Python client share *only* the contract — the byte-for-byte proof that the typed surface is the boundary.
- **REST vs gRPC vs GraphQL vs events.** A grounded comparison: gRPC for service-to-service typed RPC, REST for public/cacheable resource APIs, GraphQL (and Federation) for client-shaped aggregation over many backends, AsyncAPI/events for fire-and-forget and fan-out. Choosing with evidence, and the cost of REST drift.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                    | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Wire format; proto3 authoring; the style guide           |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Schema evolution; reserved; compatibility; codegen       |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | gRPC RPC kinds; HTTP/2; the Go server + Python client    |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Interceptors; reflection; grpcurl; REST/gRPC/GraphQL     |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Streaming endpoints; the contract-evolution drill        |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                   |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, contract-doc polish                        |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                          | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Protobuf/gRPC docs, the style guide, the buf docs, and the talks worth your time |
| [lecture-notes/01-protobuf-wire-format-and-schema-evolution.md](./02-lecture-notes/01-protobuf-wire-format-and-schema-evolution.md) | The wire format, proto3 authoring, and the schema-evolution rules that keep the promise |
| [lecture-notes/02-grpc-rpc-kinds-interceptors-and-choosing.md](./02-lecture-notes/02-grpc-rpc-kinds-interceptors-and-choosing.md) | The four RPC kinds, HTTP/2, interceptors, reflection, and REST vs gRPC vs GraphQL vs events |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-author-the-contract.md](./03-exercises/exercise-01-author-the-contract.md) | Author the `catalog.v1` `.proto`, generate Go and Python stubs, and read the wire bytes |
| [exercises/exercise-02-catalog-server.go](./03-exercises/exercise-02-catalog-server.go) | A Go gRPC server implementing `catalog.v1` with unary + server-streaming endpoints |
| [exercises/exercise-03-catalog-client.py](./03-exercises/exercise-03-catalog-client.py) | A Python gRPC client that calls the Go server — proving the contract is all they share |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-evolve-without-breaking.md](./04-challenges/challenge-01-evolve-without-breaking.md) | Evolve `catalog.v1` through three changes — two safe, one breaking — and prove which is which |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the headline contract-and-compatibility report |
| [mini-project/README.md](./07-mini-project/00-overview.md) | Replace the mini-project's HTTP boundary with a versioned `catalog.v1` gRPC contract, polyglot |

## The "the contract is the only thing they share" promise

C22 uses a recurring marker for every gRPC boundary that holds up: **a Go server and a Python client, sharing nothing but the `.proto`.** When you finish the exercises, this should be literally true — there is no shared code, no shared struct, no shared library between the two. The proof:

```bash
# The Go server and the Python client share exactly one file lineage: the schema.
$ grpcurl -plaintext localhost:50051 catalog.v1.CatalogService/GetProduct \
    -d '{"sku": "SKU-1"}'
{
  "product": {
    "sku": "SKU-1",
    "name": "Mechanical Keyboard",
    "priceCents": "7999"
  }
}
```

That `grpcurl` call uses *no generated client at all* — it asks the server for its schema via reflection and constructs the call on the fly. If `grpcurl` can call your server with only the server's own reflected schema, your contract is real and self-describing. The point of Week 5 is to make that the ordinary case — and to make a schema-breaking change *loud* (a codegen or runtime failure) instead of silent (a `null` price).

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Protobuf encoding spec** end to end until you can hand-decode a 6-byte message into its fields: <https://protobuf.dev/programming-guides/encoding/>. Then verify your decode against `protoscope`.
- Adopt **`buf`** for the whole exercise: `buf lint` (enforces the style guide), `buf breaking` (mechanically detects breaking changes against the previous version — this is the tool that turns the challenge's evolution rules into a CI check), and `buf generate`.
- Add a **bidirectional-streaming** price-ticker RPC to `catalog.v1` and implement both sides — a Go server pushing price updates and a Python client both consuming updates and sending watch/unwatch requests on the same stream.
- Implement a **gRPC interceptor** on the Go server that logs every RPC's method, duration, and status code as structured JSON. You'll extend exactly this into OpenTelemetry tracing in Week 6 — the interceptor is the hook.

## Up next

Week 6 takes this typed `catalog` and `cart` pair and makes them **production-ready**: twelve-factor configuration, structured logging, health and readiness probes, graceful shutdown, baseline OpenTelemetry traces and metrics threaded *through* the gRPC interceptor you wire this week, Kubernetes manifests, a Helm chart, and a runbook. The gRPC server you build here is the exact service you harden next week. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
