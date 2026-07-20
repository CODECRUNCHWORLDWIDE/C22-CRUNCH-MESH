# Week 5 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 6. Answer key is at the bottom — don't peek.

---

**Q1.** On the Protobuf wire, what is a field's identity — and what is the consequence for renaming?

- A) The field name; renaming breaks the wire.
- B) The field number; the name is not on the wire, so a pure rename (same number, same type) is wire-compatible.
- C) The field's position in the message; reordering breaks the wire.
- D) The field's type only; numbers are advisory.

---

**Q2.** A Protobuf field tag encodes two things in one varint. What are they?

- A) The field name hash and the length.
- B) The field number and the wire type (`(field_number << 3) | wire_type`).
- C) The message type and the field count.
- D) The checksum and the field number.

---

**Q3.** Why are field numbers 1–15 recommended for the most frequent fields?

- A) They're easier to remember.
- B) Their tag fits in a single byte (field numbers up to 15), so hot fields cost one less byte each on the wire.
- C) gRPC reserves 16+ for internal use.
- D) `protoc` rejects more than 15 fields otherwise.

---

**Q4.** An old reader (built before a new field was added) receives a message containing that new field. What happens?

- A) It crashes.
- B) It rejects the whole message.
- C) It skips the unknown field (the wire type in the tag tells it how many bytes to skip) and reads the rest — forward compatibility.
- D) It overwrites field 1 with the unknown field's bytes.

---

**Q5.** Which of these is a SAFE, wire-compatible schema change?

- A) Reusing the number of a deleted field for a new field.
- B) Changing `int64 price_cents = 3` to `Money price = 3`.
- C) Adding a new field with a brand-new field number.
- D) Renumbering an existing field from 3 to 9.

---

**Q6.** Why does proto3 have no `required` keyword?

- A) An oversight that will be fixed.
- B) Because `required` makes schema evolution impossible — you can never remove a required field without breaking old readers — so proto3 removed it deliberately; validate requiredness in code instead.
- C) Because all fields are required by default in proto3.
- D) Because gRPC handles validation automatically.

---

**Q7.** What does the `reserved` keyword protect against, and how?

- A) Nothing; it's documentation only.
- B) It marks a retired field number and/or name so that any attempt to reuse it fails to compile — turning the "reuse a number" silent corruption into a build error.
- C) It reserves memory for the field.
- D) It makes a field immutable at runtime.

---

**Q8.** You need the server to push a sequence of results the client consumes incrementally (a product feed). Which RPC kind?

- A) Unary.
- B) Server-streaming (`returns (stream Product)`).
- C) Client-streaming.
- D) Bidirectional-streaming.

---

**Q9.** Why does gRPC require HTTP/2, and what consequence does that have for browsers?

- A) HTTP/2 is just faster; no consequence.
- B) gRPC needs HTTP/2's multiplexed streams and binary framing for true streaming, and sends the final status in HTTP/2 *trailers* — which browsers' Fetch API can't read, so browsers need gRPC-Web or Connect.
- C) HTTP/2 is required only for TLS; browsers work fine with raw gRPC.
- D) gRPC uses HTTP/2 for caching; browsers cache gRPC natively.

---

**Q10.** What does server reflection enable?

- A) The server to modify its own code at runtime.
- B) A tool like `grpcurl` to call the service with no generated client, by asking the server to describe its own schema at runtime.
- C) Automatic retries.
- D) Mutual TLS.

---

**Q11.** Where should cross-cutting concerns (logging, auth, tracing) live in a gRPC server, and why?

- A) In each handler, copied; it's clearer.
- B) In an interceptor — it wraps every RPC uniformly, so logging/auth/tracing apply to all calls without touching any handler. (It's also the hook for Week 6's OpenTelemetry tracing.)
- C) In the `.proto` file.
- D) In the client only.

---

**Q12.** For an internal, service-to-service call where the caller needs an answer now, in a polyglot system, which protocol is the right default — and what's the one-line reason?

- A) REST; it's universal.
- B) GraphQL; clients shape the response.
- C) gRPC; typed contract enforced by codegen, compact binary wire, streaming, and first-class deadlines/status — ideal for internal polyglot RPC.
- D) Events; producers shouldn't block.

---

**Q13.** What is "REST drift," and how does a typed Protobuf contract address it?

- A) REST endpoints getting slower over time; Protobuf is faster.
- B) Without an enforced schema, REST APIs accrete inconsistencies (mixed naming, mixed date formats, a field that's sometimes a string and sometimes a number) that no tool catches; Protobuf makes the schema compiler-enforced, so drift becomes a build error.
- C) REST servers losing data; Protobuf persists it.
- D) REST not supporting HTTPS; Protobuf does.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The number is the wire identity; names aren't on the wire, so a pure rename is wire-safe (though a source break). (Lecture 1 §2.4, §4.2.)
2. **B** — `(field_number << 3) | wire_type` in one varint. The wire type tells the reader how to parse the value. (Lecture 1 §2.1.)
3. **B** — Field numbers up to 15 have a single-byte tag; reserve them for hot fields. A wire-format optimization. (Lecture 1 §2.2.)
4. **C** — Skip the unknown field using the wire type, read the rest. Forward compatibility. (Lecture 1 §4.1.)
5. **C** — Add with a new number. A, B, D are all breaking (reuse, type change, renumber). (Lecture 1 §4.2–4.3.)
6. **B** — `required` makes evolution impossible; proto3 removed it on purpose. Validate in code. (Lecture 1 §3.)
7. **B** — `reserved` makes recycling a retired number/name a build error. (Lecture 1 §4.4.)
8. **B** — Server-streaming: one request, a stream of responses consumed incrementally. (Lecture 2 §1.2.)
9. **B** — Multiplexing + framing for streaming; status in trailers, which browsers can't read → gRPC-Web/Connect. (Lecture 2 §2.)
10. **B** — Reflection lets tools call the service with no stub by asking the server for its schema. (Lecture 2 §3.2.)
11. **B** — Interceptors wrap every RPC uniformly; the hook for Week 6 tracing. (Lecture 2 §3.1.)
12. **C** — gRPC for internal polyglot answer-now RPC: typed, fast, streaming, deadlines. (Lecture 2 §4.1, §4.5.)
13. **B** — Unenforced schemas drift; Protobuf makes the schema compiler-enforced so drift is a build error. The "moral position" thesis. (Lecture 2 §4.2.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
