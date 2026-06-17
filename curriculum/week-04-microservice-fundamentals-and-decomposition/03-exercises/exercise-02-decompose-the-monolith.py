#!/usr/bin/env python3
# Exercise 2 — Score a proposed topology against the decomposition heuristics
#
# Goal: Turn the four heuristics from Lecture 2 into a tool. Given a proposed
#       service topology described as data, score it and flag the two anti-patterns
#       that are mechanically detectable from the spec alone — the entity service
#       and the shared database — plus warn on chatty synchronous fan-out.
#
# Estimated time: 50 minutes. Runnable.
#
# WHY A TOOL AND NOT JUST JUDGEMENT
#
#   Two of the four anti-patterns leave a fingerprint in the topology *spec*,
#   before any code is written:
#     * Shared database  -> two services list the same owned table.
#     * Entity service    -> a service whose operations are all CRUD over one table
#                            and which has no business capability verb.
#   A tool catches these on a design doc, in CI, in seconds. The distributed
#   monolith and the chatty mesh need call-graph data (Exercise 3, in Go).
#
# HOW TO USE THIS FILE
#
#       python3 exercise-02-decompose-the-monolith.py
#
#   It scores a deliberately-flawed sample topology, prints a per-service report,
#   prints the detected smells, and EXITS NON-ZERO because the sample has faults.
#   Then it scores a corrected topology and exits 0. Read both reports.
#
#   To score YOUR OWN topology: edit FLAWED_TOPOLOGY (or build a new Topology)
#   and re-run. This is the tool you run on your homework memo's proposal.
#
# ACCEPTANCE CRITERIA
#
#   [ ] Running the file prints a report for the flawed topology that flags:
#         - the shared `products` table between `catalog` and `cart`,
#         - the entity service `customer_service` (all-CRUD, noun-named),
#         - the chatty fan-out from `order`.
#   [ ] The flawed run exits non-zero; the corrected run exits 0.
#   [ ] You can explain, for each flagged smell, which Lecture 2 section names it.
#
# Standard library only. No network, no database. Expected output at the bottom.

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum


class CallKind(str, Enum):
    SYNC = "sync"    # blocking request/response (gRPC unary, HTTP)
    ASYNC = "async"  # fire-and-forget event / message


@dataclass(frozen=True)
class Operation:
    """One operation a service exposes. `crud` marks plain create/read/update/delete."""
    name: str
    crud: bool


@dataclass
class Service:
    name: str
    # Tables this service claims to OWN. Database-per-service: a table must be
    # owned by exactly one service.
    owned_tables: list[str]
    operations: list[Operation]
    # Synchronous calls this service makes, per single inbound user action, to
    # other services: {target_service: count}. Count > 1 means a loop / fan-out.
    sync_calls: dict[str, int] = field(default_factory=dict)
    async_calls: dict[str, int] = field(default_factory=dict)


@dataclass
class Topology:
    services: list[Service]

    def by_name(self) -> dict[str, Service]:
        return {s.name: s for s in self.services}


@dataclass
class Finding:
    severity: str   # "ERROR" or "WARN"
    rule: str       # short rule id
    message: str


# --- The detectors -----------------------------------------------------------


def detect_shared_database(topo: Topology) -> list[Finding]:
    """Shared-database anti-pattern (Lecture 2 §2.2): a table owned by >1 service.

    In a correct topology every table has exactly one owner. If two services list
    the same table in `owned_tables`, they are coupled at the data layer — the
    invisible coupling that no code review catches.
    """
    findings: list[Finding] = []
    owners: dict[str, list[str]] = {}
    for svc in topo.services:
        for table in svc.owned_tables:
            owners.setdefault(table, []).append(svc.name)
    for table, svc_names in sorted(owners.items()):
        if len(svc_names) > 1:
            findings.append(
                Finding(
                    "ERROR",
                    "shared-database",
                    f"table '{table}' is owned by {len(svc_names)} services "
                    f"({', '.join(sorted(svc_names))}); a table must have exactly "
                    f"one owner (database-per-service).",
                )
            )
    return findings


def detect_entity_service(topo: Topology) -> list[Finding]:
    """Entity-service anti-pattern (Lecture 2 §2.4): all-CRUD over one table, no verb.

    A service is an entity service when EVERY operation it exposes is plain CRUD
    AND it owns exactly one table AND its name reads like a bare entity noun
    (ends in '_service' or is a single noun). Such a service has no business
    capability — it's a shim over a table.
    """
    findings: list[Finding] = []
    for svc in topo.services:
        if not svc.operations:
            continue
        all_crud = all(op.crud for op in svc.operations)
        single_table = len(svc.owned_tables) == 1
        noun_named = svc.name.endswith("_service") or "_" not in svc.name
        if all_crud and single_table and noun_named:
            findings.append(
                Finding(
                    "ERROR",
                    "entity-service",
                    f"service '{svc.name}' exposes only CRUD "
                    f"({', '.join(op.name for op in svc.operations)}) over one table "
                    f"'{svc.owned_tables[0]}' and is noun-named; this is an entity "
                    f"service. Merge it into the capability that owns its behavior.",
                )
            )
    return findings


def detect_chatty_fanout(topo: Topology, threshold: int = 4) -> list[Finding]:
    """Chatty-mesh smell (Lecture 2 §2.3): too many synchronous hops per action.

    We flag a service whose total synchronous fan-out per inbound action exceeds
    `threshold`, and separately flag any single sync edge with count > 1 (a loop:
    the across-the-network N+1).
    """
    findings: list[Finding] = []
    for svc in topo.services:
        total_sync = sum(svc.sync_calls.values())
        if total_sync > threshold:
            findings.append(
                Finding(
                    "WARN",
                    "chatty-mesh",
                    f"service '{svc.name}' makes {total_sync} synchronous calls per "
                    f"action across {len(svc.sync_calls)} dependencies; latency and "
                    f"failure compound. Consider batching, async events, or coarser "
                    f"boundaries.",
                )
            )
        for target, count in sorted(svc.sync_calls.items()):
            if count > 1:
                findings.append(
                    Finding(
                        "WARN",
                        "sync-loop",
                        f"service '{svc.name}' calls '{target}' {count}x per action "
                        f"(an across-the-network N+1). Add a bulk endpoint "
                        f"(e.g. Get{target.capitalize()}s([]id)).",
                    )
                )
    return findings


# --- Scoring -----------------------------------------------------------------


def score_topology(topo: Topology) -> tuple[list[Finding], int]:
    """Run all detectors. Return (findings, exit_code). exit_code != 0 on any ERROR."""
    findings: list[Finding] = []
    findings += detect_shared_database(topo)
    findings += detect_entity_service(topo)
    findings += detect_chatty_fanout(topo)
    errors = [f for f in findings if f.severity == "ERROR"]
    return findings, (1 if errors else 0)


def report(label: str, topo: Topology) -> int:
    print(f"\n{'=' * 70}")
    print(f"TOPOLOGY: {label}  ({len(topo.services)} services)")
    print("=" * 70)
    for svc in topo.services:
        tables = ", ".join(svc.owned_tables) or "(none)"
        ops = ", ".join(op.name for op in svc.operations) or "(none)"
        sync = sum(svc.sync_calls.values())
        print(f"  {svc.name:18s} tables=[{tables}]  ops=[{ops}]  sync_calls={sync}")

    findings, code = score_topology(topo)
    print("-" * 70)
    if not findings:
        print("FINDINGS: none. Topology is clean against the mechanical checks.")
    else:
        for f in findings:
            print(f"  [{f.severity:5s}] {f.rule:16s} {f.message}")
    n_err = sum(1 for f in findings if f.severity == "ERROR")
    n_warn = sum(1 for f in findings if f.severity == "WARN")
    verdict = "FAIL (exit 1)" if code else "PASS (exit 0)"
    print("-" * 70)
    print(f"score: {n_err} ERROR, {n_warn} WARN  ->  {verdict}")
    return code


# --- Sample topologies -------------------------------------------------------

# A deliberately flawed topology: shared table, an entity service, a chatty order.
FLAWED_TOPOLOGY = Topology(
    services=[
        Service(
            name="catalog",
            owned_tables=["products", "categories"],
            operations=[
                Operation("get_product", crud=True),
                Operation("search_products", crud=False),
            ],
        ),
        Service(
            name="cart",
            # FAULT: cart also claims 'products' -> shared database with catalog.
            owned_tables=["carts", "products"],
            operations=[
                Operation("add_item", crud=False),
                Operation("checkout", crud=False),
            ],
            sync_calls={"catalog": 1, "pricing": 1},
        ),
        Service(
            name="customer_service",  # FAULT: noun-named, all CRUD, one table.
            owned_tables=["customers"],
            operations=[
                Operation("create_customer", crud=True),
                Operation("get_customer", crud=True),
                Operation("update_customer", crud=True),
                Operation("delete_customer", crud=True),
            ],
        ),
        Service(
            name="order",
            owned_tables=["orders"],
            operations=[Operation("place_order", crud=False)],
            # FAULT: chatty fan-out, and an N+1 over catalog (1 per line item).
            sync_calls={
                "cart": 1,
                "catalog": 3,   # per-line-item loop
                "pricing": 3,   # per-line-item loop
                "inventory": 1,
                "payment": 1,
            },
        ),
        Service(
            name="pricing",
            owned_tables=["promotions", "tax_rates"],
            operations=[Operation("compute_price", crud=False)],
        ),
        Service(
            name="inventory",
            owned_tables=["stock", "reservations"],
            operations=[
                Operation("reserve_stock", crud=False),
                Operation("release_stock", crud=False),
            ],
        ),
        Service(
            name="payment",
            owned_tables=["charges"],
            operations=[Operation("charge", crud=False), Operation("refund", crud=False)],
        ),
    ]
)

# The corrected topology: catalog owns products alone, customer behavior folded
# into a `billing` capability, order batches its reads and reacts to events.
FIXED_TOPOLOGY = Topology(
    services=[
        Service(
            name="catalog",
            owned_tables=["products", "categories"],
            operations=[
                Operation("get_products", crud=False),     # bulk read
                Operation("search_products", crud=False),
            ],
        ),
        Service(
            name="cart",
            owned_tables=["carts"],   # FIXED: no longer claims products
            operations=[
                Operation("add_item", crud=False),
                Operation("checkout", crud=False),
            ],
            sync_calls={"catalog": 1, "pricing": 1},  # bulk calls, 1 each
        ),
        Service(
            name="billing",  # FIXED: capability, not an entity CRUD wrapper
            owned_tables=["customers", "billing_accounts"],
            operations=[
                Operation("open_account", crud=False),
                Operation("update_billing_address", crud=False),
                Operation("charge_customer", crud=False),
            ],
        ),
        Service(
            name="order",
            owned_tables=["orders"],
            operations=[Operation("place_order", crud=False)],
            # FIXED: bulk reads (1 each), payment driven by saga; fan-out under threshold
            sync_calls={"cart": 1, "catalog": 1, "pricing": 1},
            async_calls={"inventory": 1, "payment": 1},  # saga via events
        ),
        Service(
            name="pricing",
            owned_tables=["promotions", "tax_rates"],
            operations=[Operation("compute_price", crud=False)],
        ),
        Service(
            name="inventory",
            owned_tables=["stock", "reservations"],
            operations=[
                Operation("reserve_stock", crud=False),
                Operation("release_stock", crud=False),
            ],
        ),
        Service(
            name="payment",
            owned_tables=["charges"],
            operations=[Operation("charge", crud=False), Operation("refund", crud=False)],
        ),
    ]
)


def main() -> None:
    flawed_code = report("FLAWED (the inherited Bookhive split)", FLAWED_TOPOLOGY)
    fixed_code = report("FIXED (the defended topology)", FIXED_TOPOLOGY)

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"  flawed topology exit code: {flawed_code}  (expected 1)")
    print(f"  fixed  topology exit code: {fixed_code}  (expected 0)")

    # The exercise 'passes' when the tool behaves as designed: catches the flawed
    # one, clears the fixed one. We exit on the FIXED code so this can gate CI
    # against a corrected design.
    if flawed_code == 1 and fixed_code == 0:
        print("  tool behaves correctly: it FAILS the bad split and PASSES the good one.")
        sys.exit(0)
    print("  UNEXPECTED: detector did not behave as designed; re-check your edits.")
    sys.exit(2)


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (abridged)
# -----------------------------------------------------------------------------
#
# ======================================================================
# TOPOLOGY: FLAWED (the inherited Bookhive split)  (7 services)
# ======================================================================
#   catalog            tables=[products, categories]  ops=[get_product, ...] ...
#   cart               tables=[carts, products]  ops=[add_item, checkout] ...
#   ...
# ----------------------------------------------------------------------
#   [ERROR] shared-database   table 'products' is owned by 2 services (cart, catalog); ...
#   [ERROR] entity-service    service 'customer_service' exposes only CRUD ...
#   [WARN ] chatty-mesh       service 'order' makes 9 synchronous calls per action ...
#   [WARN ] sync-loop         service 'order' calls 'catalog' 3x per action ...
#   [WARN ] sync-loop         service 'order' calls 'pricing' 3x per action ...
# ----------------------------------------------------------------------
# score: 2 ERROR, 3 WARN  ->  FAIL (exit 1)
#
# ======================================================================
# TOPOLOGY: FIXED (the defended topology)  (7 services)
# ======================================================================
#   ...
# ----------------------------------------------------------------------
# FINDINGS: none. Topology is clean against the mechanical checks.
# ----------------------------------------------------------------------
# score: 0 ERROR, 0 WARN  ->  PASS (exit 0)
#
# ======================================================================
# SUMMARY
# ======================================================================
#   flawed topology exit code: 1  (expected 1)
#   fixed  topology exit code: 0  (expected 0)
#   tool behaves correctly: it FAILS the bad split and PASSES the good one.
#
# The lesson: the shared 'products' table and the 'customer_service' CRUD wrapper
# are invisible in a diagram but obvious to a 200-line tool reading the spec.
# Run this on your homework memo's proposal before you submit it.
# -----------------------------------------------------------------------------
