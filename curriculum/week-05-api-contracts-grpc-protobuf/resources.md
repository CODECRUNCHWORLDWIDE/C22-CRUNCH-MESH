# Week 5 — Resources

Every resource here is **free** and **current to 2026**. Protobuf and gRPC are open-source projects with excellent first-party documentation; the `buf` toolchain is open-source with a free tier that covers everything in this week. No paywalled material is required. Where a spec is the authoritative source (the encoding spec, the proto3 language guide), it is linked directly, not a blog that paraphrases it.

The bias matches the course: read the spec and the official style guide, not a Medium post that got the field-numbering rules subtly wrong.

## Required reading (work it into your week)

- **Protocol Buffers — proto3 Language Guide.** The canonical reference for proto3 syntax: messages, services, scalar types, `repeated`, `map`, `oneof`, `enum`, `reserved`. Read it Monday and keep it open all week.
  <https://protobuf.dev/programming-guides/proto3/>
- **Protocol Buffers — Encoding.** The wire format at the byte level: tags, varints, length-delimited fields, zig-zag. This is Lecture 1's source. Read it until you can hand-decode a small message.
  <https://protobuf.dev/programming-guides/encoding/>
- **Protobuf — Best Practices / Style Guide.** Package naming, versioning, field-numbering discipline, the dos and don'ts that keep a schema evolvable.
  <https://protobuf.dev/best-practices/dos-donts/>
  <https://protobuf.dev/programming-guides/style/>
- **gRPC — Core Concepts.** The four RPC kinds, channels, deadlines, metadata, status codes. The conceptual spine of Lecture 2.
  <https://grpc.io/docs/what-is-grpc/core-concepts/>
- **gRPC — Introduction / "What is gRPC".** The HTTP/2 substrate, the codegen model, the polyglot story.
  <https://grpc.io/docs/what-is-grpc/introduction/>

## The specs (skim, then reference)

- **Protocol Buffers encoding spec** (linked above) — the authoritative byte format.
- **gRPC over HTTP/2 — the wire protocol.** How gRPC maps onto HTTP/2 frames, headers, and trailers. The reason gRPC-Web exists (browsers can't read HTTP/2 trailers).
  <https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md>
- **HTTP/2 (RFC 9113).** You won't read it cover to cover, but know where the multiplexing and HPACK header-compression that gRPC relies on are specified.
  <https://www.rfc-editor.org/rfc/rfc9113.html>

## Codegen toolchains (you'll have these open all week)

- **`protoc` — the reference compiler.** Plus the language plugins.
  <https://protobuf.dev/installation/>
- **Go plugins — `protoc-gen-go` and `protoc-gen-go-grpc`.** The Go quickstart shows the exact install and generate commands.
  <https://grpc.io/docs/languages/go/quickstart/>
- **Python — `grpcio` and `grpcio-tools`.** The Python quickstart; `python -m grpc_tools.protoc ...` is the generate command.
  <https://grpc.io/docs/languages/python/quickstart/>
- **`buf` — the modern Protobuf toolchain.** `buf lint`, `buf breaking` (mechanical breaking-change detection — the tool behind the challenge), `buf generate`, `buf format`. Strongly recommended over raw `protoc`.
  <https://buf.build/docs/introduction>
  <https://buf.build/docs/breaking/overview>

## Reflection, debugging, and tools

- **`grpcurl` — curl for gRPC.** Calls a service with no generated client by using server reflection. Your primary debugging tool.
  <https://github.com/fullstorydev/grpcurl>
- **gRPC Server Reflection.** How a server describes its own schema at runtime so tools can call it blind.
  <https://github.com/grpc/grpc/blob/master/doc/server-reflection.md>
- **`protoscope` — a wire-format inspector.** Decodes raw Protobuf bytes into a readable form; use it to check your hand-decodes from Lecture 1.
  <https://github.com/protocolbuffers/protobuf/tree/main/protoscope>
- **`grpcui`** — an interactive web UI for a reflection-enabled gRPC server (the gRPC analogue of Swagger UI).
  <https://github.com/fullstorydev/grpcui>

## Interceptors (the cross-cutting hook)

- **gRPC Go — interceptors.** Unary and streaming interceptors; the server- and client-side middleware model.
  <https://grpc.io/docs/languages/go/basics/>
- **`go-grpc-middleware`** — battle-tested interceptors for logging, recovery, auth, and (relevant to Week 6) OpenTelemetry tracing.
  <https://github.com/grpc-ecosystem/go-grpc-middleware>

## The comparison (REST / gRPC / GraphQL / events)

- **gRPC vs REST — the official FAQ position and community consensus.** When typed RPC beats resource-oriented HTTP, and vice versa.
  <https://grpc.io/docs/what-is-grpc/faq/>
- **GraphQL — the spec and Federation.** When client-shaped aggregation over many backends is the right tool, and what Federation adds.
  <https://graphql.org/learn/>
  <https://www.apollographql.com/docs/federation/>
- **AsyncAPI — the contract format for event-driven APIs.** The "Protobuf-of-events" analogue you'll meet properly in Weeks 10–11.
  <https://www.asyncapi.com/docs>
- **Connect (by Buf) — gRPC-compatible RPC that also speaks plain HTTP.** The modern answer to "I want gRPC semantics but a browser-friendly transport."
  <https://connectrpc.com/docs/introduction>

## Talks worth your time (free, no signup)

- **"gRPC Deep Dive" and Protobuf-internals talks — CNCF / gRPC channel.** The maintainers explaining the HTTP/2 mapping and the wire format.
  <https://www.youtube.com/@CloudNativeFdn>
- **Buf's "Protobuf and the future of API design" talks.** The case for schema-first, breaking-change detection, and the registry model.
  <https://www.youtube.com/@bufbuild>
- **"REST vs gRPC vs GraphQL" comparison talks (various, GOTO / InfoQ).** Watch one with a skeptical eye; the honest ones say "it depends, here's on what."
  <https://www.youtube.com/@GOTO->

## Tools you'll use this week

- **`protoc`** or **`buf`** — compile `.proto` to Go and Python.
- **`protoc-gen-go`, `protoc-gen-go-grpc`** (Go) and **`grpcio-tools`** (Python) — the language plugins.
- **`grpcurl`** — call your server with no client. `grpcurl -plaintext localhost:50051 list`.
- **`buf lint` / `buf breaking`** — enforce the style guide and detect breaking changes in CI.
- **`protoscope`** — inspect raw wire bytes.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Protobuf** | Protocol Buffers — Google's schema-defined binary serialization format. |
| **`.proto`** | The schema file: messages, services, RPCs. The contract. |
| **Field number (tag)** | The integer that identifies a field on the wire. **Never reused, never changed.** |
| **Wire type** | The 3-bit code (varint, 64-bit, length-delimited, 32-bit) telling the reader how to parse a field. |
| **Varint** | Variable-length integer encoding; small numbers take fewer bytes. |
| **Length-delimited** | Encoding for strings, bytes, and embedded messages: a length prefix then the bytes. |
| **`reserved`** | Keyword marking retired field numbers/names so they can never be recycled. |
| **Backward-compatible** | A new server can read messages written by old clients. |
| **Forward-compatible** | An old reader can read messages written by a new writer (skips unknown fields). |
| **gRPC** | The RPC framework over HTTP/2 that uses Protobuf for messages. |
| **Unary RPC** | One request, one response. |
| **Server-streaming** | One request, a stream of responses. |
| **Client-streaming** | A stream of requests, one response. |
| **Bidi-streaming** | Two independent streams in both directions. |
| **Stub** | Generated client/server code from a `.proto`. |
| **Reflection** | A server describing its own schema at runtime so tools call it without a stub. |
| **Interceptor** | gRPC middleware — wraps every RPC for logging, auth, tracing. |
| **`grpcurl`** | curl for gRPC; uses reflection to call without a generated client. |

---

*If a link 404s, please open an issue so we can replace it.*
