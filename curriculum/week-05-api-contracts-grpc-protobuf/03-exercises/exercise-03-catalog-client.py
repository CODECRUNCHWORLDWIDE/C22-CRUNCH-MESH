#!/usr/bin/env python3
# Exercise 3 — The Python gRPC client for catalog.v1
#
# Goal: Call the GO server from Exercise 2 using a PYTHON client, proving the
#       contract (the .proto) is the only thing the two share. The client
#       exercises all three RPC kinds the server implements: unary GetProduct,
#       bulk BatchGetProducts, and server-streaming ListProducts. It also shows
#       correct handling of a gRPC status code (NOT_FOUND) and a deadline.
#
# Estimated time: 45 minutes. Runnable once Exercise 1's Python stubs exist and
#                 the Exercise 2 Go server is running.
#
# PREREQUISITES
#
#   1. `python3 -m pip install grpcio grpcio-tools`
#   2. The Python stubs from Exercise 1 importable:
#        catalog/v1/catalog_pb2.py        (messages)
#        catalog/v1/catalog_pb2_grpc.py   (the service stub)
#      Adjust the import below to match how you generated them. If you generated
#      flat (--python_out=. with -I catalog/v1), use:
#          import catalog_pb2, catalog_pb2_grpc
#   3. The Go server from Exercise 2 running on localhost:50051.
#
# RUN
#
#        # terminal 1: the Go server
#        go run exercise-02-catalog-server.go
#        # terminal 2: this client
#        python3 exercise-03-catalog-client.py
#
# ACCEPTANCE CRITERIA
#
#   [ ] GetProduct("SKU-1") returns the Mechanical Keyboard with price 7999.
#   [ ] GetProduct("NOPE") raises grpc.RpcError with code StatusCode.NOT_FOUND,
#       which the client handles gracefully (not a crash).
#   [ ] BatchGetProducts(["SKU-1","SKU-3","NOPE"]) returns the two known products
#       in one call; the unknown one is simply absent.
#   [ ] ListProducts(category="peripherals") streams products one at a time.
#   [ ] The whole run prints PASS. The Go server logged each call via its
#       interceptor — Go server, Python client, ONE shared .proto.
#
# Expected output is at the bottom of the file.

import sys

import grpc

# Adjust to match your generated layout. Package layout (recommended):
try:
    from catalog.v1 import catalog_pb2, catalog_pb2_grpc
except ImportError:
    # Flat layout fallback (--python_out=. -I catalog/v1).
    import catalog_pb2  # type: ignore
    import catalog_pb2_grpc  # type: ignore

SERVER = "localhost:50051"
DEADLINE_SECONDS = 5.0


def get_product(stub: "catalog_pb2_grpc.CatalogServiceStub", sku: str):
    """Unary call. Returns the Product, or None if the server says NOT_FOUND."""
    try:
        resp = stub.GetProduct(
            catalog_pb2.GetProductRequest(sku=sku),
            timeout=DEADLINE_SECONDS,  # a deadline — gRPC cancels if it overruns
        )
        return resp.product
    except grpc.RpcError as e:
        # The error is a typed gRPC status code, part of the contract.
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return None
        raise  # any other code is a real failure; let it surface


def batch_get(stub, skus: list[str]):
    """Unary bulk call — many SKUs in ONE round trip (the chatty-mesh fix)."""
    resp = stub.BatchGetProducts(
        catalog_pb2.BatchGetProductsRequest(skus=skus),
        timeout=DEADLINE_SECONDS,
    )
    return list(resp.products)


def list_products(stub, category: str):
    """Server-streaming call — consume Products one at a time as they arrive."""
    out = []
    # The stub returns an iterator; each next() yields one streamed Product.
    for product in stub.ListProducts(
        catalog_pb2.ListProductsRequest(category=category),
        timeout=DEADLINE_SECONDS,
    ):
        out.append(product)
    return out


def main() -> None:
    # An insecure channel for local dev. In Week 6+ this becomes mTLS via the mesh.
    with grpc.insecure_channel(SERVER) as channel:
        stub = catalog_pb2_grpc.CatalogServiceStub(channel)
        failures = 0

        # 1) Unary, found.
        p = get_product(stub, "SKU-1")
        if p and p.sku == "SKU-1" and p.price_cents == 7999:
            print(f"[unary]   GetProduct(SKU-1) -> {p.name} @ {p.price_cents}c  OK")
        else:
            print(f"[unary]   GetProduct(SKU-1) -> unexpected: {p}  FAIL")
            failures += 1

        # 2) Unary, NOT_FOUND handled gracefully.
        missing = get_product(stub, "NOPE")
        if missing is None:
            print("[unary]   GetProduct(NOPE) -> NOT_FOUND handled gracefully  OK")
        else:
            print(f"[unary]   GetProduct(NOPE) -> expected None, got {missing}  FAIL")
            failures += 1

        # 3) Bulk: one round trip, unknown SKU simply absent.
        batch = batch_get(stub, ["SKU-1", "SKU-3", "NOPE"])
        got_skus = sorted(p.sku for p in batch)
        if got_skus == ["SKU-1", "SKU-3"]:
            print(f"[bulk]    BatchGetProducts([3]) -> {got_skus} in 1 call  OK")
        else:
            print(f"[bulk]    BatchGetProducts -> unexpected {got_skus}  FAIL")
            failures += 1

        # 4) Server-streaming.
        streamed = list_products(stub, "peripherals")
        names = sorted(p.name for p in streamed)
        if len(streamed) >= 2 and all(p.category == "peripherals" for p in streamed):
            print(f"[stream]  ListProducts(peripherals) -> {len(streamed)} streamed: {names}  OK")
        else:
            print(f"[stream]  ListProducts -> unexpected {names}  FAIL")
            failures += 1

        print("-" * 60)
        if failures == 0:
            print("PASS: Go server + Python client interoperated over one .proto.")
            print("      They share NO code. The contract is the only thing in common.")
            sys.exit(0)
        print(f"FAIL: {failures} check(s) failed. Is the Go server running on {SERVER}?")
        sys.exit(1)


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Expected output (with the Exercise 2 Go server running)
# -----------------------------------------------------------------------------
#
# [unary]   GetProduct(SKU-1) -> Mechanical Keyboard @ 7999c  OK
# [unary]   GetProduct(NOPE) -> NOT_FOUND handled gracefully  OK
# [bulk]    BatchGetProducts([3]) -> ['SKU-1', 'SKU-3'] in 1 call  OK
# [stream]  ListProducts(peripherals) -> 3 streamed: ['Mechanical Keyboard', 'USB-C Hub', 'Wireless Mouse']  OK
# ------------------------------------------------------------
# PASS: Go server + Python client interoperated over one .proto.
#       They share NO code. The contract is the only thing in common.
#
# Meanwhile the GO server logged, via its interceptor:
#   {"level":"INFO","msg":"grpc_call","method":".../GetProduct","code":"OK",...}
#   {"level":"INFO","msg":"grpc_call","method":".../GetProduct","code":"NotFound",...}
#   {"level":"INFO","msg":"grpc_call","method":".../BatchGetProducts","code":"OK",...}
#   {"level":"INFO","msg":"grpc_call","method":".../ListProducts","code":"OK",...}
#
# That is the typed surface: two languages, one contract, no shared code, and a
# NOT_FOUND that is a status code rather than a 200-with-an-error-field. The
# whole point of Week 5, demonstrated end to end.
# -----------------------------------------------------------------------------
