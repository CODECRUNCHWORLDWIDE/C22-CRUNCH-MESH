# Challenge 1 — Classify Four Designs and Fix the Dual-Writer

**Time estimate:** ~90 minutes.

## Problem statement

You are the staff engineer reviewing four teams' event-architecture proposals. Each team uses events, and each *thinks* they understand what kind of system they're building. Your job — the real job — is to (1) correctly classify each design in the Lecture 2 taxonomy, (2) find the one design that contains a **dual-write time bomb** that will silently corrupt state in production, and (3) rewrite that one to be safe. Then, for each design, judge whether it picked the right tool for its actual problem.

This mirrors the real skill: you rarely get to design an event system from a blank page. You inherit four of them, written by people with different and often wrong mental models, and you have to name what each *actually* is before you can reason about it.

## The four designs

### Design A — "Notifications service"

> When a user changes their email, the `users` service runs, in one request handler: `UPDATE users SET email=? WHERE id=?;` then `kafka.produce("UserEmailChanged", {...})`. A downstream `notifications` service consumes `UserEmailChanged` and sends a confirmation email. The `users` table is the source of truth; the event is a notification.

### Design B — "Order search"

> The `orders` service writes to a normalized Postgres `orders` schema (the source of truth). A Debezium connector captures the `orders` change stream to Kafka. A `search` service consumes that stream and maintains a denormalized Elasticsearch index of orders-with-customer-and-items, used only for the search page. Searches tolerate a few seconds of staleness. The Elasticsearch index is rebuilt from scratch by replaying the stream whenever the mapping changes.

### Design C — "Ledger"

> The `ledger` service has no `accounts` table with a `balance` column. Instead it has an append-only `ledger_events` table: `MoneyDeposited`, `MoneyWithdrawn`, `TransferInitiated`, `TransferCompleted`. An account's current balance is computed by replaying its events. A withdrawal command loads the account's events, folds them to a balance, checks the balance is sufficient, and appends a `MoneyWithdrawn` event with `expected_version`. Auditors require the full history of every balance change, forever.

### Design D — "Inventory cache"

> The `inventory` service handles a reservation by: `UPDATE inventory SET available = available - 1 WHERE sku=? AND available > 0;` (the source of truth), and then, in the same handler after the update commits, `kafka.produce("InventoryReserved", {sku, ...})` so the `analytics` and `reorder` services can react. If the produce fails, it logs an error and moves on.

## Your task

For **each design A–D**, produce:

1. **Classification** — exactly one of: *event-driven service*, *CDC-fed CQRS*, *event-sourced aggregate*. Justify it against the taxonomy table (where is the source of truth? where do events come from? is current state stored or folded?).
2. **Right tool?** — does this design fit its stated problem, or is it over- or under-engineered? One or two sentences.
3. **Dual-write check** — does this design contain a dual write (a non-atomic "write the DB, then publish")? Yes/no, and exactly where.

Then:

4. **Fix the bomb.** Identify the one design with the dangerous dual write, explain the specific failure interleaving that corrupts state, and rewrite it two ways: (a) with the transactional outbox pattern (show the SQL/pseudocode of the one-transaction write + the relay), and (b) with log-based CDC (show what you'd capture instead). State which you'd ship and why.

## Acceptance criteria

- [ ] A file `challenge-01-classification.md` with a section per design containing parts 1–3, plus the part-4 fix.
- [ ] Your classifications are correct:
  - **A** — *event-driven service* (users table is truth; event is a notification). **It has a dual write.**
  - **B** — *CDC-fed CQRS* (normalized write model; Debezium-derived stream; denormalized rebuildable read model). No dual write. Right tool.
  - **C** — *event-sourced aggregate* (the event log IS the source of truth; balance is folded; optimistic-concurrency append). No dual write. Right tool — history is a hard requirement.
  - **D** — *event-driven service* with a **dual write** (update inventory, then produce; produce can fail after the commit).
- [ ] You correctly identify that **both A and D dual-write**, and you fix at least **D** (the more dangerous one, because a lost `InventoryReserved` desyncs analytics and reorder from real stock). Bonus for fixing A too.
- [ ] For the fix, the outbox version shows the business write and the outbox row in **one transaction**, and you explain why the relay's at-least-once delivery is safe given idempotent consumers.
- [ ] You explicitly state that **C is NOT over-engineered** even though event sourcing is usually overkill — because the audit-history requirement is exactly the case where its costs are worth paying.
- [ ] Committed to your Week 14 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

There are two traps, and most reviewers fall into one.

**Trap 1: "Design A is fine because the event is just a notification."** It is not fine. A is a genuine dual write: if the process crashes between `UPDATE users` and `kafka.produce`, the email changed but no `UserEmailChanged` event fired, so no confirmation email is sent — and worse, any *other* consumer of that event (an audit log, a downstream cache) silently misses the change forever. "It's just a notification" does not exempt you from atomicity. The fix is the same outbox/CDC as D.

**Trap 2: "Design C should use a normal table with a balance column; event sourcing is over-engineering."** Usually that critique is right — but not here. C's *requirement* is "auditors require the full history of every balance change, forever." That is precisely the case event sourcing exists for: the history *is* the asset, and a mutable `balance` column throws it away. Recommending "just use a balance column" here is the wrong call. The discipline is to apply your "event sourcing is usually overkill" instinct *and* recognize the minority case where it isn't.

The whole challenge is calibration: catch the dual writes (A and D) without false-positiving on the safe designs (B and C), and judge event sourcing's fit by the *requirement*, not by reflex.

## Stretch

- **Build and break Design D.** Implement the dual-write version, run it, kill the process between the commit and the produce (a `kill -9` in the right window, or a deliberate `panic()` after commit), and show analytics drifting from real stock. Then implement the outbox fix and show the drift is gone.
- **Quantify A's blast radius.** If `UserEmailChanged` also feeds a fraud-detection cache, write one paragraph on the downstream consequence of a single lost event — to make "it's just a notification" concretely indefensible.
- **Design C's GDPR problem.** C keeps every balance event forever. A user invokes the right to erasure. Write the design note: how do you honor erasure against an append-only ledger you're legally required to retain? (Crypto-shredding vs. PII-outside-the-log — discuss the tension with the audit requirement.)

## Why this matters

In the Phase 3 architecture review, the reviewer will point at a box-and-arrow diagram and ask "is this CQRS or event sourcing?" and "where's your dual write?" — and a wrong answer to either reveals you don't actually understand the system you drew. This challenge *is* that conversation, four times over. Every event-driven platform accumulates designs from people with fuzzy mental models; the engineer who can classify them correctly and spot the dual-write bomb before it ships is the one whose platform doesn't quietly corrupt itself.
