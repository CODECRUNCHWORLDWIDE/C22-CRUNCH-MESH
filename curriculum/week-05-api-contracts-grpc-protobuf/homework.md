# Week 5 Homework

Six problems that revisit the week's topics and force the contract discipline into your fingers. The full set should take about **5 hours**. Work in your Week 5 Git repository (the same workspace as the exercises and the gRPC mini-project) so every problem produces at least one commit you can point to at the Phase 1 architecture review in Week 12.

The headline deliverable is **Problem 4 — the contract-and-compatibility report**, called out explicitly in the syllabus. Treat it as the artifact a reviewer reads before approving a service's API, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Go 1.23+**, **Python 3.12+**, and **`buf` (or `protoc`)** available. Problems 1–6 use the `catalog.v1` contract and the exercises' generated stubs.

---

## Problem 1 — Hand-decode and verify

**Problem statement.** Encode three `catalog.v1.Product` messages of your choosing (different SKUs, names, prices). For each, write out the raw bytes in hex, then **hand-decode them back** to fields using the Lecture 1 §2 rules (tag → field number + wire type; varints; length-delimited). Verify every decode with `protoscope`. Write it to `notes/week-05/wire-decode.md`.

**Acceptance criteria.**

- `notes/week-05/wire-decode.md` has three messages, each with its hex bytes, your hand-decode, and the matching `protoscope` output.
- For at least one message, you point out explicitly that the field *names* are absent from the bytes.
- You state in one sentence why this absence is what makes renaming wire-safe and number-reuse catastrophic.
- Committed.

**Hint.** Pick a product with a small price (e.g. 5) and a larger one (e.g. 28900) so you see a one-byte varint and a multi-byte varint. `protoscope` reads from stdin: `python3 -c "..." | protoscope`.

**Estimated time.** 40 minutes.

---

## Problem 2 — Classify ten schema changes

**Problem statement.** For each of the ten proposed changes to `catalog.v1` below, classify it **SAFE** (wire-compatible, both directions) or **BREAKING**, and give the one-line reason. Then verify your classification of *at least four* of them with `buf breaking`. Write it to `notes/week-05/change-classification.md`.

1. Add `bool in_stock = 7;`
2. Rename `price_cents` to `amount_cents` (same number 3, same type).
3. Change `price_cents` from `int64` (field 3) to `double`.
4. Add a new RPC `CountProducts(...)` to the service.
5. Delete field 4 (`description`) and reserve its number and name.
6. Delete field 4 (`description`) WITHOUT reserving.
7. Change field 5 (`category`) from `string` to a `repeated string`.
8. Add a new value `OUT_OF_STOCK = 3` to an existing enum (with `_UNSPECIFIED = 0`).
9. Reuse field number 4 for a new `int32 weight_grams = 4;` (after deleting `description`, unreserved).
10. Move `name` from field 2 to field 9.

**Acceptance criteria.**

- All ten classified with a one-line reason each.
- At least four verified against `buf breaking` (output pasted).
- You correctly identify the subtle ones: #5 vs #6 (reserving doesn't change wire-compat of the deletion itself, but protects the *future*), #2 (wire-safe but a source break), #9 (the cardinal sin).
- Committed.

**Hint.** Build a tiny git history: commit the baseline, apply a change, run `buf breaking --against '.git#ref=HEAD~1'`. The tool is the answer key — but predict first, then verify, or you learn nothing.

**Estimated time.** 50 minutes.

---

## Problem 3 — Add a streaming RPC and call it from both languages

**Problem statement.** Add a **client-streaming** RPC to `catalog.v1`: `UploadProducts(stream Product) returns (UploadSummary)` where `UploadSummary` has `int32 imported` and `int32 rejected`. Implement it on the Go server (Exercise 2) and call it from the Python client (Exercise 3), uploading several products and printing the summary. Capture both sides.

**Acceptance criteria.**

- The `.proto` has the new RPC and message; regenerated stubs build on both sides.
- The Go server implements `UploadProducts`, counting imported vs rejected (reject e.g. an empty SKU).
- The Python client streams several products and prints the returned summary.
- `notes/week-05/client-streaming.md` shows the run on both sides.
- Committed.

**Hint.** In Python, client-streaming is `stub.UploadProducts(iterator_of_requests)`. In Go, the handler receives a stream and loops `stream.Recv()` until `io.EOF`, then `stream.SendAndClose(summary)`. This is the inverse of the server-streaming `ListProducts` you already have.

**Estimated time.** 1 hour.

---

## Problem 4 — The contract-and-compatibility report (headline deliverable)

**Problem statement.** This is the syllabus deliverable. Write a report at `notes/week-05/contract-report.md` that documents `catalog.v1` as a *production* contract a reviewer would approve. It must contain:

1. **The contract.** The full `catalog.proto`, with a sentence on each style decision (versioned package, `int64` money, well-known types, field-number discipline, no `required`).
2. **The compatibility policy.** Your rules for evolving it: what changes are allowed without a version bump, what forces a `v2`, and how `buf breaking` enforces this in CI.
3. **A worked evolution.** Take one additive change through the full proof: `buf breaking` says compatible, AND a running old client keeps working (with output). Take one breaking change through the full proof: `buf breaking` flags it, AND a running old client fails (with output), AND the correct fix is a `v2` (shown).
4. **The polyglot proof.** Evidence that a Go server and a Python client interoperate over the contract sharing no code — the `grpcurl` reflection cross-check, and the grep showing no shared code.
5. **The choice justification.** Two paragraphs: why gRPC for this internal boundary rather than REST or GraphQL, naming the boundary's properties (internal, answer-now, polyglot, fixed contract). This is the design-review answer (Lecture 2 §4).

**Acceptance criteria.**

- `notes/week-05/contract-report.md` exists and hits all five sections.
- The worked evolution shows *both* the safe and the breaking case with *real* `buf breaking` output and a running-client demonstration.
- The choice justification names the boundary's properties, not "because gRPC is good."
- Committed.

**Hint.** Sections 3 and 4 are where this report is won — they're *demonstrations*, not assertions. The strongest version reuses your challenge work: paste the actual `buf breaking` outputs and the old-client behavior. A reviewer believes a pasted tool output; they don't believe "trust me, it's compatible."

**Estimated time.** 1 hour 15 minutes.

---

## Problem 5 — Wire the contract gate into CI

**Problem statement.** Add a `buf breaking` (and `buf lint`) check to your repo's CI (a GitHub Action, or a `make breaking` target you run pre-push). Then prove the gate works: open a branch with a deliberately-breaking change and show the check *fails*; fix it (or version it to `v2`) and show the check *passes*. Capture both in `notes/week-05/contract-gate.md`.

**Acceptance criteria.**

- A CI config (`.github/workflows/contract.yml`) or a documented `make breaking` target exists.
- `notes/week-05/contract-gate.md` shows a failing run (the breaking change blocked) and a passing run (after the fix/version).
- You state in one sentence why a *bot* enforcing the rules beats *engineers remembering* them.
- Committed.

**Hint.** `buf breaking --against '.git#branch=main'` is the core command. The failing run is the deliverable — a green CI on a breaking change means your gate isn't wired right. Make it *fail* on the bad change first; that's the proof it works.

**Estimated time.** 35 minutes.

---

## Problem 6 — Choose the right tool for four boundaries

**Problem statement.** For each of these four boundaries from the capstone marketplace, choose gRPC, REST, GraphQL, or events, and justify in two sentences naming the boundary's properties (Lecture 2 §4). Write it to `notes/week-05/protocol-choices.md`.

1. `order` calls `inventory` to reserve stock and needs an immediate yes/no.
2. A public product-detail API consumed by third-party affiliate sites and browsers, heavily cached.
3. A mobile app's home screen needs "cart + line items + product names + recommended items" in one round trip.
4. `cart` emits "checked out"; `order`, `analytics`, and `email` all need to react, and `cart` must not wait on any of them.

**Acceptance criteria.**

- `notes/week-05/protocol-choices.md` has a choice + two-sentence justification for each.
- The justifications name properties (internal/public, answer-now/notify, fixed/client-shaped, cacheable), not preferences.
- You correctly land: 1→gRPC, 2→REST, 3→GraphQL/BFF, 4→events.
- Committed.

**Hint.** The tell for #4 is "must not wait on any of them" — that's the decoupled-in-time property that means events. The tell for #2 is "browsers + cached" — that's REST. The tell for #3 is "varied client needs in one round trip" — that's GraphQL.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Hand-decode and verify | 40 min |
| 2 — Classify ten changes | 50 min |
| 3 — Streaming RPC, both languages | 1 h 0 min |
| 4 — Contract-and-compatibility report (headline) | 1 h 15 min |
| 5 — Contract gate in CI | 35 min |
| 6 — Choose the right tool | 30 min |
| **Total** | **~4 h 50 min** |

---

## Rubric (for the headline report, Problem 4)

| Criterion | Excellent (full) | Adequate (half) | Missing (zero) |
|---|---|---|---|
| **Contract quality** | Every style decision justified; `buf lint` clean; versioned package; `int64` money. | Contract present, some decisions unexplained. | Style violations (float money, no version). |
| **Compatibility policy** | Clear allowed/forbidden rules tied to `buf breaking`; `v2` trigger defined. | Rules present but vague. | No policy. |
| **Worked evolution** | Both safe and breaking cases shown with real `buf breaking` output AND running-client behavior. | One case shown, or asserted not demonstrated. | Assertions only. |
| **Polyglot proof** | `grpcurl` reflection + no-shared-code grep, both shown. | One shown. | Claimed, not shown. |
| **Choice justification** | Names the boundary's properties; defends gRPC over REST/GraphQL with evidence. | Justifies but with preference, not properties. | "Because gRPC is good." |

**Full marks across the board** is the artifact you bring to the Week 12 architecture review. Anything less, revise before then — you'll defend the contract live.

When you've finished all six, push your repo and make sure the gRPC [mini-project](./mini-project/README.md) is in the same workspace — Week 6 hardens it into production. Then take the [quiz](./quiz.md) with your notes closed.
