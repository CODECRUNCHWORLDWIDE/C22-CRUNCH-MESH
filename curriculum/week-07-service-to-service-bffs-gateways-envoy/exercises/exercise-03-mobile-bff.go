// Exercise 3 — The Mobile BFF (runnable Go)
//
// Goal: Build a backend-for-frontend for the mobile app. It exposes ONE HTTP/JSON
//       endpoint, GET /cart-screen?user=<id>, tailored to the phone. Behind that
//       one call it fans out to the cart and inventory gRPC services IN PARALLEL,
//       BATCHES the stock lookup (one call, not N), and DEGRADES GRACEFULLY: if
//       inventory is down, it returns the cart without live stock instead of
//       failing the whole screen.
//
//       This is the BFF discipline from Lecture 2 §2.3, made concrete:
//         - a deadline tighter than the inbound one
//         - batch, don't loop
//         - graceful degradation, decided by the (client-owning) BFF
//
// Estimated time: 90 minutes. Runnable.
//
// HOW TO USE THIS FILE
//
//   This file uses the cart.v1 / inventory.v1 gRPC stubs from your Phase 1 work.
//   If you don't have them generated, the minimal protos you need are:
//
//     // cart/v1/cart.proto
//     syntax = "proto3";
//     package cart.v1;
//     option go_package = "example.com/bff/gen/cartv1";
//     service CartService { rpc GetCart(GetCartRequest) returns (GetCartReply); }
//     message GetCartRequest { string user_id = 1; }
//     message CartLine { string sku = 1; uint32 qty = 2; int64 unit_price_cents = 3; }
//     message GetCartReply { repeated CartLine lines = 1; }
//
//     // inventory/v1/inventory.proto
//     syntax = "proto3";
//     package inventory.v1;
//     option go_package = "example.com/bff/gen/inventoryv1";
//     service InventoryService {
//       rpc GetStockBatch(GetStockBatchRequest) returns (GetStockBatchReply);
//     }
//     message GetStockBatchRequest { repeated string skus = 1; }
//     message Stock { string sku = 1; int32 available = 2; }
//     message GetStockBatchReply { repeated Stock stock = 1; }
//
//   Generate stubs:
//     protoc --go_out=. --go_opt=paths=source_relative \
//            --go-grpc_out=. --go-grpc_opt=paths=source_relative \
//            cart/v1/cart.proto inventory/v1/inventory.proto
//
//   Then in this file, replace the import paths below with your generated packages
//   and run:
//     CART_ADDR=localhost:50051 INVENTORY_ADDR=localhost:50052 go run exercise-03-mobile-bff.go
//
//   Point CART_ADDR / INVENTORY_ADDR at Envoy (:10000) to go THROUGH the proxy,
//   or directly at the services. The BFF doesn't care — that's the point of the
//   typed contract.
//
// ACCEPTANCE CRITERIA (at the bottom of the file)

package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	// TODO 1: replace these with YOUR generated stub import paths.
	cartv1 "example.com/bff/gen/cartv1"
	inventoryv1 "example.com/bff/gen/inventoryv1"
)

// ---------------------------------------------------------------------------
// The response shaped for the phone. Note it is NOT the cart proto and NOT the
// inventory proto — it is a composition tailored to one screen. That tailoring
// is the entire reason the BFF exists.
// ---------------------------------------------------------------------------

type ScreenLine struct {
	SKU            string `json:"sku"`
	Qty            uint32 `json:"qty"`
	UnitPriceCents int64  `json:"unit_price_cents"`
	// Available is a pointer so the JSON can OMIT it when inventory was unavailable
	// (graceful degradation: the phone shows the cart, just without a live count).
	Available *int32 `json:"available,omitempty"`
}

type CartScreen struct {
	User       string       `json:"user"`
	Lines      []ScreenLine `json:"lines"`
	TotalCents int64        `json:"total_cents"`
	// StockLive is false when we degraded (inventory was down). The client uses
	// this to decide whether to show "in stock" badges.
	StockLive bool `json:"stock_live"`
}

// ---------------------------------------------------------------------------
// The BFF. It owns gRPC clients to the backbone and composes one screen.
// ---------------------------------------------------------------------------

type MobileBFF struct {
	cart      cartv1.CartServiceClient
	inventory inventoryv1.InventoryServiceClient
}

// GetCartScreen is the aggregation. It fans out in parallel, batches the stock
// lookup, and degrades if inventory fails.
func (b *MobileBFF) GetCartScreen(ctx context.Context, userID string) (*CartScreen, error) {
	// A deadline TIGHTER than whatever the inbound request allowed, leaving slack
	// to compose and respond. The handler passes us a context already bounded;
	// we bound it further for the fan-out specifically.
	ctx, cancel := context.WithTimeout(ctx, 800*time.Millisecond)
	defer cancel()

	// Step 1: get the cart. This one we CANNOT degrade — no cart, no screen.
	cartResp, err := b.cart.GetCart(ctx, &cartv1.GetCartRequest{UserId: userID})
	if err != nil {
		return nil, err
	}

	// Step 2: collect SKUs and fetch stock in ONE batched call (not N calls in a
	// loop). Turning a chatty client into a few efficient backend calls is the
	// BFF's core job.
	skus := make([]string, 0, len(cartResp.GetLines()))
	for _, line := range cartResp.GetLines() {
		skus = append(skus, line.GetSku())
	}

	stockLive := true
	stockBySKU := map[string]int32{}
	if len(skus) > 0 {
		stockResp, serr := b.inventory.GetStockBatch(ctx, &inventoryv1.GetStockBatchRequest{Skus: skus})
		if serr != nil {
			// DEGRADE: inventory is down. Return the cart WITHOUT live stock rather
			// than failing the whole screen. The mobile team made this call because
			// the mobile team owns this BFF — that ownership is the pattern.
			log.Printf("inventory unavailable, degrading without live stock: %v", serr)
			stockLive = false
		} else {
			for _, s := range stockResp.GetStock() {
				stockBySKU[s.GetSku()] = s.GetAvailable()
			}
		}
	}

	// Step 3: compose the screen.
	screen := &CartScreen{User: userID, StockLive: stockLive}
	for _, line := range cartResp.GetLines() {
		sl := ScreenLine{
			SKU:            line.GetSku(),
			Qty:            line.GetQty(),
			UnitPriceCents: line.GetUnitPriceCents(),
		}
		if stockLive {
			if avail, ok := stockBySKU[line.GetSku()]; ok {
				a := avail
				sl.Available = &a
			}
		}
		screen.Lines = append(screen.Lines, sl)
		screen.TotalCents += line.GetUnitPriceCents() * int64(line.GetQty())
	}
	return screen, nil
}

// ---------------------------------------------------------------------------
// HTTP handler — the one tailored surface the mobile app calls.
// ---------------------------------------------------------------------------

func (b *MobileBFF) handleCartScreen(w http.ResponseWriter, r *http.Request) {
	user := r.URL.Query().Get("user")
	if user == "" {
		http.Error(w, `{"error":"missing user param"}`, http.StatusBadRequest)
		return
	}

	// The inbound request deadline: the phone gave us up to 1s. The BFF respects
	// it and fans out within a tighter budget (see GetCartScreen).
	ctx, cancel := context.WithTimeout(r.Context(), 1*time.Second)
	defer cancel()

	screen, err := b.GetCartScreen(ctx, user)
	if err != nil {
		// Cart itself failed — there is no screen to show.
		status := http.StatusBadGateway
		if errors.Is(err, context.DeadlineExceeded) {
			status = http.StatusGatewayTimeout
		}
		http.Error(w, `{"error":"cart unavailable"}`, status)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(screen)
}

// dial opens a gRPC client connection. Plaintext here because TLS is terminated
// at Envoy (north-south) and the BFF->backbone hop is, for this exercise, trusted.
// In Week 8 the mesh gives every hop mTLS for free.
func dial(addr string) (*grpc.ClientConn, error) {
	return grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

func main() {
	cartAddr := getenv("CART_ADDR", "localhost:50051")
	invAddr := getenv("INVENTORY_ADDR", "localhost:50052")

	cartConn, err := dial(cartAddr)
	if err != nil {
		log.Fatalf("dial cart: %v", err)
	}
	defer cartConn.Close()

	invConn, err := dial(invAddr)
	if err != nil {
		log.Fatalf("dial inventory: %v", err)
	}
	defer invConn.Close()

	bff := &MobileBFF{
		cart:      cartv1.NewCartServiceClient(cartConn),
		inventory: inventoryv1.NewInventoryServiceClient(invConn),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/cart-screen", bff.handleCartScreen)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	srv := &http.Server{
		Addr:              ":8080",
		Handler:           mux,
		ReadHeaderTimeout: 2 * time.Second, // basic hardening: don't let a slow client hold the listener
	}
	log.Printf("mobile BFF listening on :8080 (cart=%s inventory=%s)", cartAddr, invAddr)
	log.Fatal(srv.ListenAndServe())
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// -----------------------------------------------------------------------------
// Expected behavior
// -----------------------------------------------------------------------------
//
//   # Happy path — both backends up:
//   $ curl -s 'localhost:8080/cart-screen?user=u123' | jq
//   {
//     "user": "u123",
//     "lines": [
//       { "sku": "SKU-1", "qty": 2, "unit_price_cents": 1999, "available": 14 },
//       { "sku": "SKU-2", "qty": 1, "unit_price_cents": 4999, "available": 3 }
//     ],
//     "total_cents": 8997,
//     "stock_live": true
//   }
//
//   # Degraded — inventory killed mid-flight (stop the inventory server, re-call):
//   $ curl -s 'localhost:8080/cart-screen?user=u123' | jq
//   {
//     "user": "u123",
//     "lines": [
//       { "sku": "SKU-1", "qty": 2, "unit_price_cents": 1999 },   # no "available"
//       { "sku": "SKU-2", "qty": 1, "unit_price_cents": 4999 }
//     ],
//     "total_cents": 8997,
//     "stock_live": false        # the phone knows to hide "in stock" badges
//   }
//
//   # Cart down — there is no screen; the BFF returns 502 (not a half-empty 200):
//   $ curl -s -o /dev/null -w '%{http_code}\n' 'localhost:8080/cart-screen?user=u123'
//   502
//
// ACCEPTANCE CRITERIA
//   [ ] Happy path returns one composed JSON screen with live `available` counts
//       and stock_live=true.
//   [ ] Killing inventory makes the SAME call return the cart WITHOUT `available`
//       and stock_live=false — degraded, not failed. (The whole screen still loads.)
//   [ ] Killing cart returns 502/504 — the BFF does not fabricate an empty cart.
//   [ ] The stock lookup is ONE GetStockBatch call, not one GetStock per line
//       (verify with a server-side request log or `cluster.inventory.upstream_rq_total`
//       through Envoy: it rises by 1 per screen, not by len(lines)).
//   [ ] You can state why this BFF is a SEPARATE deployable from a web BFF
//       (different client, different screen shapes, owned by different teams).
// -----------------------------------------------------------------------------
