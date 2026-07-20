# Challenge 1 — Evolve `catalog.v1` Without Breaking the Consumers

**Time estimate:** ~90 minutes.

## Problem statement

You own the `catalog.v1` contract. Three product requests land on your desk in one sprint:

1. **"Add an `in_stock` flag to products."** Marketing wants to grey out sold-out items.
2. **"Add a `currency` so we can sell in EUR."** Finance is expanding to the EU.
3. **"Change `price_cents` to a proper `Money` message with amount + currency, and drop the separate fields."** A staff engineer thinks the two-field approach is ugly and wants one clean `Money`.

Two of these can be done compatibly. One cannot. Your job is to **make all three changes, prove which are safe and which is breaking using a still-running old client and `buf breaking`, and ship the safe ones while correctly versioning the breaking one** — without ever silently breaking a consumer.

This mirrors the real skill: product doesn't know or care which changes are wire-compatible. The contract owner is the one who knows, before shipping, whether a change is a free additive deploy or a fleet-wide migration. Getting this wrong is the canonical "we shipped on Friday and prod broke" incident.

## Setup

You need, from the exercises:

- `catalog/v1/catalog.proto` (the contract).
- The generated Go server (Exercise 2) running, and the Python client (Exercise 3).
- `buf` installed (`buf breaking` is the mechanical detector you'll lean on).
- A git commit of the *current* `catalog.proto` to diff against (`buf breaking` compares against a ref).

Commit the baseline first:

```bash
git add catalog/v1/catalog.proto && git commit -m "baseline catalog.v1"
```

## Part A — The two safe changes (additive)

Apply changes 1 and 2 as **additive** fields with new field numbers:

```proto
message Product {
  string sku          = 1;
  string name         = 2;
  int64  price_cents  = 3;
  string description  = 4;
  string category     = 5;
  google.protobuf.Timestamp updated_at = 6;
  bool   in_stock     = 7;   // change 1: NEW field, new number
  string currency     = 8;   // change 2: NEW field, new number (e.g. "USD")
}
```

**Prove they're safe two ways:**

1. **`buf breaking`** must report **no breaking changes** against the baseline:
   ```bash
   buf breaking --against '.git#ref=HEAD'
   # (no output / exit 0 = compatible)
   ```
2. **A still-running old client** must keep working. Keep your *old* generated Python stubs (pre-change), regenerate only the *server* against the new schema, restart the server, and run the *old* client. It must still get products — it simply won't see `in_stock`/`currency` (it skips the unknown fields, Lecture 1 §4.1). Capture that the old client still succeeds.

This is forward compatibility, demonstrated on running code.

## Part B — The breaking change (and how to version it)

Now attempt change 3 the way the staff engineer asked — *in place*, on field 3:

```proto
// DO NOT SHIP THIS as catalog.v1. It is here to prove it breaks.
message Money {
  int64  amount_minor = 1;
  string currency     = 2;
}

message Product {
  string sku   = 1;
  string name  = 2;
  Money  price = 3;   // BREAKING: field 3 was int64 (varint), now a message (LEN)
  // ...
}
```

**Prove it breaks two ways:**

1. **`buf breaking`** must **flag it** — field 3 changed wire type (varint → length-delimited) and changed name/type. Capture the exact `buf breaking` error.
2. **A running old client** must *fail or misread* — an old client built when field 3 was `int64` receives a `Money` (a length-delimited message) on tag `(3<<3)|2` where it expected `(3<<3)|0`. Capture the failure (a parse error, or a garbage value). This is the §4.3 cardinal sin made visible.

**Now version it correctly.** A change this shape cannot be made compatibly on `v1`. The right move is a **new package, `catalog.v2`**, that coexists with `v1`:

- Create `catalog/v2/catalog.proto` with the `Money`-based `Product`.
- The server implements *both* `catalog.v1.CatalogService` and `catalog.v2.CatalogService` (register both on the same gRPC server) during the migration window.
- Old `v1` clients keep calling `v1`; new clients call `v2`; you retire `v1` only after every consumer has migrated.

Demonstrate the server serving both `v1` and `v2` simultaneously (`grpcurl ... list` shows both services).

## Part C — Reserve the retired field

In `catalog.v1` (the one you keep serving), suppose you *do* eventually remove `description` (field 4). Reserve its number and name so no future engineer can recycle them:

```proto
message Product {
  reserved 4;
  reserved "description";
  string sku          = 1;
  string name         = 2;
  int64  price_cents  = 3;
  string category     = 5;
  google.protobuf.Timestamp updated_at = 6;
  bool   in_stock     = 7;
  string currency     = 8;
}
```

Prove the guardrail works: try to add `bool foo = 4;` and confirm `buf`/`protoc` **refuses to compile**. Capture that refusal. That refusal is the difference between a silent future corruption and a build error.

## Acceptance criteria

- [ ] A file `challenge-01-evolution.md` documenting all three parts with the actual command outputs pasted in.
- [ ] **Part A:** `buf breaking` reports compatible for the two additive changes, AND a running old client keeps working against the new server (with evidence).
- [ ] **Part B:** `buf breaking` *flags* the in-place `price` change with its exact error, AND a running old client fails/misreads it (with evidence); then the server serves both `catalog.v1` and `catalog.v2` (shown via `grpcurl ... list`).
- [ ] **Part C:** `description` is reserved (number and name); an attempt to add `bool foo = 4;` fails to compile, with the error captured.
- [ ] You can state, in one sentence each: why changes 1 and 2 are free, why change 3 is not, and why `reserved` matters.
- [ ] Committed to your Week 5 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The seductive wrong move in Part B is to "fix" the breaking change by keeping field number 3 but just renaming `price_cents` to `price` and changing its type, reasoning "it's the same concept, the same slot." But the wire matches by *number and wire type*, not concept (Lecture 1 §2.4, §4.3). Field 3 as a varint and field 3 as a length-delimited message are *incompatible on the wire* no matter what you call them. The concept being "the same" is exactly the trap — the bytes don't know about concepts. If your instinct was to reuse slot 3 for `Money`, you fell in; the right answer is `v2`.

A second trap: trying to make change 2 (`currency`) by *splitting* `price_cents` into amount+currency within `v1`. That's change 3 wearing change 2's clothes — it touches field 3's type and breaks. Adding a *separate* `currency` field (number 8) is additive and safe; *restructuring* `price_cents` is not. The difference between "add a field" and "restructure a field" is the difference between a free deploy and a fleet migration.

## Stretch

- Wire `buf breaking` into a **GitHub Action** on the `catalog` repo so any PR that breaks the contract fails CI automatically. This is how real shops prevent the Friday incident — the contract owner doesn't have to remember the rules; the bot enforces them on every PR.
- Implement a **`v1`→`v2` translation** in the server: the `v2` handler computes `Money{amount_minor: price_cents, currency: "USD"}` from the `v1` data, so a single backing store serves both contracts. This is the realistic migration shape — one source of truth, two contract versions.
- Add an `enum` to `catalog.v1` (e.g. `ProductStatus { PRODUCT_STATUS_UNSPECIFIED = 0; ACTIVE = 1; DISCONTINUED = 2; }`), then add a value (`OUT_OF_STOCK = 3;`) and prove with an old client that an unrecognized enum value is *preserved as its integer* in proto3, not rejected (Lecture 1 §4.2). The mandatory `_UNSPECIFIED = 0` zero value is the subtle style rule here — explain why it must exist.

## Why this matters

In Week 12 you defend your `cart` system's API versioning at the Phase 1 architecture review. The reviewer will not ask you to recite the evolution rules — they'll point at a contract change in your git history and ask "was that safe, and how did you know before you shipped it?" This challenge *is* that conversation, rehearsed. Every service you'll ever own has consumers you can't redeploy atomically, and the engineer who knows — mechanically, with `buf breaking`, not by careful reading — whether a change is safe is the one who ships on Friday without fear.
