# Week 5 — Exercises

Three exercises that take you from a `.proto` to a running polyglot gRPC pair. Do them in order — exercise 1 produces the contract and the generated stubs that exercises 2 and 3 depend on. The first is guided (author + generate + read the bytes); the second is a Go server; the third is a Python client that calls it.

## Index

1. **[Exercise 1 — Author the contract](./exercise-01-author-the-contract.md)** — write the `catalog.v1` `.proto`, generate Go and Python stubs, and decode a real message on the wire with `protoscope`. (~50 min, guided)
2. **[Exercise 2 — The Go gRPC server](./exercise-02-catalog-server.go)** — a Go server implementing `catalog.v1` with a unary `GetProduct`, a bulk `BatchGetProducts`, a server-streaming `ListProducts`, a logging interceptor, and reflection. (~50 min, runnable once stubs are generated)
3. **[Exercise 3 — The Python gRPC client](./exercise-03-catalog-client.py)** — a Python client that calls the Go server, proving the contract is the only thing they share. (~45 min, runnable once stubs are generated)

## How to work the exercises

- Have **Go 1.23+**, **Python 3.12+**, and **`protoc` or `buf`** installed. Exercise 1 walks the install of the codegen plugins.
- The order matters: exercise 1 generates the stubs that 2 and 3 import. Do not skip it.
- The Go server (exercise 2) and the Python client (exercise 3) **share no code** — only the `.proto` and the stubs each generates *from* it. That is the whole demonstration. Resist any urge to share a struct or a helper between them.
- Each runnable exercise ends with an **expected output** block, including the `grpcurl` cross-check. If your output doesn't match, you're not done.
- When a call "doesn't work," check in this order: is the server up (`grpcurl ... list`)? does the method name match exactly (`catalog.v1.CatalogService/GetProduct`)? are both sides built from the *same* `.proto` version? This is the gRPC analogue of the Week-4 boundary-debugging discipline.

## The codegen step (do this once, in exercise 1)

Both the Go server and the Python client are generated *from* `catalog/v1/catalog.proto`. Exercise 1 produces:

- Go: `gen/catalogv1/*.pb.go` and `*_grpc.pb.go` (via `protoc-gen-go` + `protoc-gen-go-grpc`).
- Python: `catalog_pb2.py` and `catalog_pb2_grpc.py` (via `python -m grpc_tools.protoc`).

Exercises 2 and 3 import these. If you adopt `buf` (recommended), `buf generate` produces both from one `buf.gen.yaml`.

## Running, once stubs are generated

```bash
# Terminal 1: the Go server
go run exercise-02-catalog-server.go

# Terminal 2: the Python client
python3 exercise-03-catalog-client.py

# Terminal 3: the no-client cross-check
grpcurl -plaintext localhost:50051 catalog.v1.CatalogService/GetProduct -d '{"sku":"SKU-1"}'
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-05` to compare.
