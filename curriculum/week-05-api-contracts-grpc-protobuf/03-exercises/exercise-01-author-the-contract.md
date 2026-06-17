# Exercise 1 — Author the Contract

**Goal:** Write the `catalog.v1` Protobuf contract by hand, generate Go and Python stubs from it, and decode a real message on the wire so the bytes from Lecture 1 stop being theoretical. You will produce the artifact the next two exercises depend on, and you'll prove to yourself that field *numbers*, not names, are the identity.

**Estimated time:** 50 minutes. Guided.

---

## Setup — install the toolchain

You need `protoc` (or `buf`) plus the Go and Python plugins. Pick one path.

### Path A — `buf` (recommended)

```bash
# Install buf (macOS/Linux). See https://buf.build/docs/installation
brew install bufbuild/buf/buf      # or the curl install from the docs
buf --version
```

### Path B — raw `protoc`

```bash
# protoc itself (https://protobuf.dev/installation/)
brew install protobuf               # or apt-get install -y protobuf-compiler

# Go plugins
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
# ensure $(go env GOPATH)/bin is on your PATH

# Python tooling
python3 -m pip install grpcio grpcio-tools

protoc --version
```

---

## Step 1 — Write the contract

Create `catalog/v1/catalog.proto`. Type it by hand — do not paste blindly; the point is to internalize the structure.

```proto
syntax = "proto3";

package catalog.v1;

option go_package = "github.com/crunchmesh/catalog/gen/catalogv1;catalogv1";

import "google/protobuf/timestamp.proto";

// A product as the catalog context models it.
message Product {
  string sku          = 1;   // stable business key; field 1, the hottest field
  string name         = 2;
  int64  price_cents  = 3;   // money in minor units; NEVER a float
  string description  = 4;   // cart does not use this — forces an ACL downstream
  string category     = 5;
  google.protobuf.Timestamp updated_at = 6;
}

message GetProductRequest  { string sku = 1; }
message GetProductResponse { Product product = 1; }

message BatchGetProductsRequest  { repeated string skus = 1; }
message BatchGetProductsResponse { repeated Product products = 1; }

message ListProductsRequest {
  string category  = 1;
  int32  page_size = 2;
}

service CatalogService {
  // Unary: one product by SKU.
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
  // Unary, bulk: many products in one round trip (the chatty-mesh fix).
  rpc BatchGetProducts(BatchGetProductsRequest) returns (BatchGetProductsResponse);
  // Server-streaming: a feed of products in a category.
  rpc ListProducts(ListProductsRequest) returns (stream Product);
}
```

Read it against Lecture 1 §3: versioned package, `int64` money, deliberate field numbers, a well-known `Timestamp`, no `required`. Every choice is defended there.

---

## Step 2 — Generate the Go stubs

### With `buf`

Create `buf.gen.yaml`:

```yaml
version: v2
plugins:
  - remote: buf.build/protocolbuffers/go
    out: gen
    opt: paths=source_relative
  - remote: buf.build/grpc/go
    out: gen
    opt: paths=source_relative
```

```bash
buf generate
```

### With raw `protoc`

```bash
protoc \
  --go_out=gen --go_opt=paths=source_relative \
  --go-grpc_out=gen --go-grpc_opt=paths=source_relative \
  catalog/v1/catalog.proto
```

You should now have `gen/catalog/v1/catalog.pb.go` (the messages) and `catalog_grpc.pb.go` (the service stub). Open `catalog.pb.go` and find the `Product` struct — note that each field has a struct tag like `protobuf:"bytes,1,opt,name=sku"`. The `1` is the field number from your `.proto`. The wire identity, made visible in the generated code.

---

## Step 3 — Generate the Python stubs

```bash
python3 -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  catalog/v1/catalog.proto
```

This produces `catalog/v1/catalog_pb2.py` (messages) and `catalog/v1/catalog_pb2_grpc.py` (the service stub). The Go and Python stubs were generated from the *same* `.proto` — that's why a Go server and a Python client will interoperate with zero shared code.

> If Python import paths fight you (the generated `catalog_pb2_grpc.py` imports `catalog_pb2`), the simplest fix for the exercise is to generate into a flat directory: `--python_out=. --grpc_python_out=.` with `-I catalog/v1` and `catalog.proto`. The mini-project shows the clean package layout.

---

## Step 4 — Read the bytes (the Lecture 1 payoff)

Now prove that field numbers are the wire identity. Encode a `Product` and look at the raw bytes.

In Python:

```python
from catalog.v1 import catalog_pb2

p = catalog_pb2.Product(sku="A", name="Pen", price_cents=300)
raw = p.SerializeToString()
print(raw.hex(" "))
# 0a 01 41 12 03 50 65 6e 18 ac 02
```

Decode it by hand against Lecture 1 §2.4:

- `0a` = `(1<<3)|2` → field 1 (`sku`), length-delimited. `01` → 1 byte. `41` → `"A"`.
- `12` = `(2<<3)|2` → field 2 (`name`), length-delimited. `03` → 3 bytes. `50 65 6e` → `"Pen"`.
- `18` = `(3<<3)|0` → field 3 (`price_cents`), varint. `ac 02` → 300.

Now the load-bearing observation: **the strings `"sku"`, `"name"`, `"price_cents"` are nowhere in those bytes.** Only the numbers 1, 2, 3. Verify with `protoscope`:

```bash
python3 -c "from catalog.v1 import catalog_pb2; import sys; sys.stdout.buffer.write(catalog_pb2.Product(sku='A',name='Pen',price_cents=300).SerializeToString())" | protoscope
# 1: {"A"}
# 2: {"Pen"}
# 3: 300
```

`protoscope` shows fields *by number* because that's all the wire carries. This is why renaming a field is wire-safe and reusing a number is catastrophic (Lecture 1 §4).

---

## Step 5 — Prove the forward-compatibility rule yourself

Add a field to the schema with a *new* number:

```proto
message Product {
  // ... existing fields 1-6 ...
  bool in_stock = 7;   // NEW
}
```

Regenerate Python stubs. Encode a `Product` *with* `in_stock=true`, serialize it, then decode those bytes with the **old** generated class (keep a copy of the pre-change `catalog_pb2.py`, or use a fresh message type missing field 7). The old reader will *skip* field 7 — it lands in the message's unknown-fields set, not an error. That skip is forward compatibility, and you just watched it happen.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `catalog/v1/catalog.proto` exists and compiles clean (`buf lint` passes if you use buf).
- [ ] Go stubs (`*.pb.go`, `*_grpc.pb.go`) and Python stubs (`*_pb2.py`, `*_pb2_grpc.py`) are generated from the same `.proto`.
- [ ] You hand-decoded the `{sku:"A", name:"Pen", price_cents:300}` message to its 11 bytes and confirmed with `protoscope` that the field *names* are absent.
- [ ] You added `in_stock = 7`, regenerated, and confirmed an old reader *skips* the unknown field rather than erroring (forward compatibility).
- [ ] You can state in one sentence why reusing field number 4 for a new field would be catastrophic (the wire matches by number; an old writer's bytes would be misread as the new field).

---

## Stretch

- Run `buf lint` and fix anything it flags — it enforces the style guide from Lecture 1 §3 (package naming, no nested enums leaking, etc.).
- Add a `reserved 4; reserved "description";` block (pretend you removed `description`) and try to add `bool foo = 4;`. Watch `protoc`/`buf` *refuse to compile*. That refusal is the `reserved` guardrail (Lecture 1 §4.4).
- Decode a message with a `repeated string skus = 1` field (from `BatchGetProductsRequest`) and observe how repeated strings are encoded — each element gets its own tag-length-value (strings aren't packed).

---

When the contract is generated and you've read the bytes, move to [Exercise 2 — The Go gRPC server](./exercise-02-catalog-server.go).
