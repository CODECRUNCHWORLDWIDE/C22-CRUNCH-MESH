// Exercise 2 — The Go gRPC server for catalog.v1
//
// Goal: Implement the CatalogService contract you authored in Exercise 1, in Go,
//       with a unary GetProduct, a bulk BatchGetProducts, a server-streaming
//       ListProducts, a logging INTERCEPTOR (the hook for Week 6 tracing), and
//       server REFLECTION (so grpcurl can call it with no client). The Python
//       client in Exercise 3 will call this exact server — sharing nothing but
//       the .proto.
//
// Estimated time: 50 minutes. Runnable once the stubs from Exercise 1 exist.
//
// PREREQUISITES
//
//   1. Exercise 1's stubs generated into ./gen (package catalogv1).
//   2. A go.mod with the gRPC + protobuf deps:
//
//        go mod init github.com/crunchmesh/catalog
//        go get google.golang.org/grpc@latest
//        go get google.golang.org/protobuf@latest
//
//   3. Put this file at the module root (or adjust the import path below to match
//      your generated package).
//
// RUN
//
//        go run exercise-02-catalog-server.go
//        # listens on :50051
//
//   Cross-check with NO generated client, using reflection:
//
//        grpcurl -plaintext localhost:50051 list
//        grpcurl -plaintext localhost:50051 \
//            catalog.v1.CatalogService/GetProduct -d '{"sku":"SKU-1"}'
//        grpcurl -plaintext localhost:50051 \
//            catalog.v1.CatalogService/ListProducts -d '{"category":"peripherals"}'
//
// ACCEPTANCE CRITERIA
//
//   [ ] `grpcurl ... list` shows catalog.v1.CatalogService (reflection works).
//   [ ] GetProduct returns SKU-1; an unknown SKU returns gRPC NOT_FOUND.
//   [ ] BatchGetProducts returns the requested known SKUs in one call.
//   [ ] ListProducts streams the products of a category one message at a time.
//   [ ] Every call logs a structured line via the interceptor (method, code, ms).
//
// NOTE on the import path: the generated package's import path is whatever you
// set in `option go_package` in Exercise 1. Here we assume:
//
//        github.com/crunchmesh/catalog/gen/catalogv1  (alias catalogv1)
//
// Adjust the single import line below if yours differs.
//
// Expected output is at the bottom of the file.

package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	// The stubs generated in Exercise 1. Change this path to match your
	// option go_package if you used a different module path.
	catalogv1 "github.com/crunchmesh/catalog/gen/catalogv1"
)

const listenAddr = ":50051"

// catalogServer implements catalogv1.CatalogServiceServer. The embedded
// Unimplemented...Server gives forward compatibility: if the .proto adds an RPC
// you haven't implemented yet, the server still compiles and returns Unimplemented
// for it rather than failing to build. (A small Lecture-1 evolution lesson in Go.)
type catalogServer struct {
	catalogv1.UnimplementedCatalogServiceServer
	products map[string]*catalogv1.Product
}

func newCatalogServer() *catalogServer {
	now := timestamppb.New(time.Now())
	seed := []*catalogv1.Product{
		{Sku: "SKU-1", Name: "Mechanical Keyboard", PriceCents: 7999, Category: "peripherals", Description: "Tactile, hot-swappable.", UpdatedAt: now},
		{Sku: "SKU-2", Name: "Wireless Mouse", PriceCents: 4599, Category: "peripherals", Description: "Ergonomic, 70h battery.", UpdatedAt: now},
		{Sku: "SKU-3", Name: "27in Monitor", PriceCents: 28900, Category: "displays", Description: "4K, 144Hz.", UpdatedAt: now},
		{Sku: "SKU-4", Name: "USB-C Hub", PriceCents: 3299, Category: "peripherals", Description: "7-in-1.", UpdatedAt: now},
	}
	m := make(map[string]*catalogv1.Product, len(seed))
	for _, p := range seed {
		m[p.Sku] = p
	}
	return &catalogServer{products: m}
}

// GetProduct: unary. Returns NOT_FOUND (a real gRPC status code) for an unknown
// SKU — not a nil product, not an error string. Status codes are part of the
// contract.
func (s *catalogServer) GetProduct(
	ctx context.Context, req *catalogv1.GetProductRequest,
) (*catalogv1.GetProductResponse, error) {
	if req.GetSku() == "" {
		return nil, status.Error(codes.InvalidArgument, "sku is required")
	}
	p, ok := s.products[req.GetSku()]
	if !ok {
		return nil, status.Errorf(codes.NotFound, "product %q not found", req.GetSku())
	}
	return &catalogv1.GetProductResponse{Product: p}, nil
}

// BatchGetProducts: unary, bulk. The chatty-mesh fix — many SKUs in one round
// trip. Unknown SKUs are silently omitted (a partial result), which is the right
// semantics for a bulk read; the caller compares requested vs returned.
func (s *catalogServer) BatchGetProducts(
	ctx context.Context, req *catalogv1.BatchGetProductsRequest,
) (*catalogv1.BatchGetProductsResponse, error) {
	resp := &catalogv1.BatchGetProductsResponse{}
	for _, sku := range req.GetSkus() {
		if p, ok := s.products[sku]; ok {
			resp.Products = append(resp.Products, p)
		}
	}
	return resp, nil
}

// ListProducts: server-streaming. Pushes one Product at a time for a category.
// The client starts consuming the first before the last is produced.
func (s *catalogServer) ListProducts(
	req *catalogv1.ListProductsRequest, stream catalogv1.CatalogService_ListProductsServer,
) error {
	sent := 0
	for _, p := range s.products {
		if req.GetCategory() != "" && p.Category != req.GetCategory() {
			continue
		}
		if err := stream.Send(p); err != nil {
			return err // client went away; propagate
		}
		sent++
		if req.GetPageSize() > 0 && int32(sent) >= req.GetPageSize() {
			break
		}
	}
	return nil
}

// loggingInterceptor wraps every unary RPC: it runs the handler, then logs the
// method, the resulting gRPC status code, and the duration as structured JSON.
// This is the cross-cutting hook; in Week 6 it becomes the OpenTelemetry span.
func loggingInterceptor(
	ctx context.Context, req any,
	info *grpc.UnaryServerInfo, handler grpc.UnaryHandler,
) (any, error) {
	start := time.Now()
	resp, err := handler(ctx, req)
	slog.Info("grpc_call",
		"method", info.FullMethod,
		"code", status.Code(err).String(),
		"duration_ms", time.Since(start).Milliseconds(),
	)
	return resp, err
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		slog.Error("listen failed", "addr", listenAddr, "err", err)
		os.Exit(1)
	}

	server := grpc.NewServer(grpc.UnaryInterceptor(loggingInterceptor))
	catalogv1.RegisterCatalogServiceServer(server, newCatalogServer())

	// Reflection: lets grpcurl/grpcui call this server with NO generated client.
	reflection.Register(server)

	fmt.Printf("catalog.v1 gRPC server listening on %s (reflection enabled)\n", listenAddr)
	if err := server.Serve(lis); err != nil {
		slog.Error("serve failed", "err", err)
		os.Exit(1)
	}
}

// -----------------------------------------------------------------------------
// Expected output (server side)
// -----------------------------------------------------------------------------
//
// catalog.v1 gRPC server listening on :50051 (reflection enabled)
// {"time":"...","level":"INFO","msg":"grpc_call","method":"/catalog.v1.CatalogService/GetProduct","code":"OK","duration_ms":0}
// {"time":"...","level":"INFO","msg":"grpc_call","method":"/catalog.v1.CatalogService/GetProduct","code":"NotFound","duration_ms":0}
//
// Expected grpcurl cross-check (no generated client — reflection only):
// -----------------------------------------------------------------------------
//
//   $ grpcurl -plaintext localhost:50051 list
//   catalog.v1.CatalogService
//   grpc.reflection.v1.ServerReflection
//
//   $ grpcurl -plaintext localhost:50051 \
//       catalog.v1.CatalogService/GetProduct -d '{"sku":"SKU-1"}'
//   {
//     "product": {
//       "sku": "SKU-1",
//       "name": "Mechanical Keyboard",
//       "priceCents": "7999",
//       "category": "peripherals",
//       "description": "Tactile, hot-swappable."
//     }
//   }
//
//   $ grpcurl -plaintext localhost:50051 \
//       catalog.v1.CatalogService/GetProduct -d '{"sku":"NOPE"}'
//   ERROR:
//     Code: NotFound
//     Message: product "NOPE" not found
//
// The NotFound is a real gRPC status code, not a 200 with an error field. That
// is the typed surface: the error is part of the contract.
// -----------------------------------------------------------------------------
