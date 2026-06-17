# Lecture 1 — SPIFFE, SPIRE, Workload Identity, and Attestation

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain zero trust and why identity is the perimeter; describe the SPIFFE ID, SVID, and trust bundle; deploy and reason about SPIRE (server, agent, node attestation, workload attestation); explain why SPIFFE/SPIRE has *no secret zero*; and explain automatic SVID rotation and why short lifetimes are a security feature.

If you remember one sentence from this lecture, remember this one:

> **Zero trust replaces "is this request from inside the network?" with "can this workload cryptographically prove who it is?" — and SPIFFE is the standard identity, SPIRE the runtime that issues it from *attestation* rather than a held secret, so there is no credential to steal.**

In Week 8, Istio gave you mTLS "for free" and the certs carried a SPIFFE identity you mostly didn't think about. This week you stop taking the identity for granted and operate it directly. The skill that makes you dangerous with zero trust is understanding that the *identity* — verifiable, attested, short-lived — is the whole foundation: encryption without identity is just a private channel to an unknown party, and authorization without identity is rules about an entity you can't verify. SPIFFE/SPIRE is how you get the identity right, and everything else (mTLS, OPA policy) builds on it.

---

## 1. Zero trust: the perimeter is dead

### 1.1 The fiction of the trusted inside

The traditional security model is a **perimeter**: a hard shell (firewall, VPN, the cluster boundary) around a soft, trusted inside. Once a request is "inside," it's trusted — services call each other freely, because they're all on the same trusted network. This model has one catastrophic failure mode: **the moment an attacker gets *one* foothold inside, they have *everything*.** A compromised dependency, a leaked token, a single exploited pod — and now the attacker is "inside the trusted network," and the network trusts them, so they move **laterally** to every other service. The breach reports you read — the ones where "attackers gained initial access via X and then moved laterally to the customer database" — are perimeter-trust failures. The inside was never actually safe; it was just *assumed* safe.

### 1.2 The zero-trust replacement

**Zero trust** (formalized in NIST SP 800-207, pioneered in Google's BeyondCorp) discards the trusted inside entirely. Its core tenet:

> **No workload is trusted because of where it is. Every workload must prove its identity, and every access must be authorized against an explicit policy — on every request, regardless of network location.**

The consequences:

- **There is no "inside."** A request from a pod in the same namespace is treated with the same suspicion as one from the public internet: prove who you are, and be authorized for this specific action.
- **A foothold buys nothing.** An attacker who compromises a pod gets *that pod's* identity and *that pod's* authorizations — not the run of the network. If the compromised pod is `frontend`, and policy says `frontend` may not call `payment`, then a `frontend` compromise *cannot* reach `payment`, full stop. Lateral movement is denied by policy, not prevented by a perimeter that's already been breached.

The reframing — **"identity is the new perimeter"** — means the security boundary moved from the *network edge* to *each workload's verifiable identity*. And that's only as strong as the identity is: if the identity can be forged or stolen, zero trust collapses. So the first, foundational problem is **how to give every workload an identity that can't be forged and isn't a secret to steal** — which is exactly SPIFFE/SPIRE.

### 1.3 The five tenets, in plain terms

NIST SP 800-207 formalizes zero trust as a set of tenets; the ones that matter for this week, in plain English:

- **No implicit trust by location.** Being "in the cluster" grants nothing. Every request is treated as if it came from a hostile network.
- **Authenticate every request.** Each request carries a verifiable identity (the SVID), checked every time — not "logged in once."
- **Authorize every request dynamically, before access.** Even an authenticated identity is checked against policy *per request* before it's allowed (the OPA gate, Lecture 2).
- **Least privilege.** Each identity gets exactly the access it needs and no more — so a compromise is confined to that identity's narrow authorizations.
- **Assume breach.** Design as if an attacker is already inside. The question isn't "how do we keep them out" but "when they get one foothold, how small is the blast radius?"

The last one is the mindset shift: **zero trust assumes the attacker is already in.** That's not pessimism — it's realism (breaches happen), and it reframes the whole design. Instead of one strong wall (which fails completely the moment it's breached), you have identity + authorization at every hop, so a breach of one workload stays a breach of *one workload*. The rest of this week — SPIFFE identity, OPA authorization, admission control — is the machinery that makes "assume breach, confine the blast radius" real.

Note how directly this connects to Week 8's mesh mTLS: there you turned on STRICT mTLS so every hop was encrypted and identified, and wrote `AuthorizationPolicy` for deny-by-default access. That *was* zero trust at the mesh layer. This week deepens it: the *identity* comes from a dedicated SPIRE deployment (more control, attestation you operate) instead of istiod's built-in CA, and the *authorization* moves to OPA/Rego (portable, testable policy-as-code) instead of mesh CRDs. Same shape — verified identity plus explicit authorization — with the two halves made explicit, operable, and stronger.

---

## 2. SPIFFE: the standard for workload identity

**SPIFFE** (Secure Production Identity Framework For Everyone) is a *standard* — not a product — for what a workload identity *is*. Three pieces.

### 2.1 The SPIFFE ID

A **SPIFFE ID** is a URI that names a workload:

```
spiffe://<trust-domain>/<workload-path>
   e.g.  spiffe://shop/ns/shop/sa/cart
         └ trust domain ┘ └─ path identifying the workload ─┘
```

- The **trust domain** (`shop`) is the identity boundary — typically one per organization or security domain. SVIDs from a *different* trust domain are not trusted unless the domains are explicitly **federated** (the multi-region stretch). The trust domain is what keeps two independent systems from accidentally authenticating each other's workloads.
- The **path** identifies the specific workload within the domain. In Kubernetes it's commonly derived from the namespace and service account (`/ns/shop/sa/cart`), which is why **service-account hygiene matters** (Week 8 §5.3): the identity is at service-account granularity, so one service, one service account.

The SPIFFE ID is just a *name* — like a username. The proof that a workload *is* that name is the SVID.

### 2.2 The SVID — the credential that proves the ID

A **SVID** (SPIFFE Verifiable Identity Document) is the credential carrying a SPIFFE ID in a verifiable form:

- **X.509-SVID:** an X.509 certificate with the SPIFFE ID in a **URI Subject Alternative Name**. This is what mTLS uses — when `cart` presents its X.509-SVID, the peer reads `spiffe://shop/ns/shop/sa/cart` out of the URI SAN and *cryptographically verifies* it (the cert is signed by the trust domain's CA). This is the same machinery Istio used in Week 8; now you control where it comes from.
- **JWT-SVID:** a JWT with the SPIFFE ID in the `sub` claim, for cases where you're authenticating to something that speaks tokens, not mTLS (an API gateway, a cloud service).

The SVID is what makes the identity *verifiable* — anyone with the trust bundle can confirm "yes, this is genuinely `spiffe://shop/ns/shop/sa/cart`, signed by the trust domain's CA, and the holder proved possession of the private key." A SPIFFE ID without a valid SVID is an unverified *claim*; with the SVID it's *proof*.

### 2.3 The trust bundle

The **trust bundle** is the set of CA certificates that validate SVIDs in a trust domain. To verify that `cart`'s SVID is genuine, a peer needs the trust domain's CA cert — that's the trust bundle. It's the root of trust: validate an SVID against the bundle and you know it's real. In federation, you exchange trust bundles between domains so each can validate the other's SVIDs (the multi-region case).

```
   issuance + verification
   SPIRE CA  ──signs──>  cart's SVID (SPIFFE ID in URI SAN)
       │                      │ presented over mTLS
       └── trust bundle ──> peer validates the SVID against the bundle
                            "yes, this is genuinely spiffe://shop/ns/shop/sa/cart"
```

### 2.4 What an X.509-SVID actually looks like

To demystify "the SPIFFE ID lives in the URI SAN," here's what you see when you decode a real X.509-SVID:

```
$ openssl x509 -in svid.pem -noout -text
Certificate:
    ...
    Subject:                                         # often EMPTY — identity isn't in the CN
    X509v3 extensions:
        X509v3 Subject Alternative Name:
            URI:spiffe://shop/ns/shop/sa/cart        # <-- the SPIFFE ID, here
        X509v3 Key Usage: critical
            Digital Signature
        X509v3 Extended Key Usage:
            TLS Web Server Authentication, TLS Web Client Authentication
    ...
    Not Before: ...                                  # short-lived: notAfter is
    Not After : ... (≈1 hour later)                  #   ~an hour out (§4)
```

Two things to notice. First, the identity is in the **URI SAN**, *not* the Subject/CN — SPIFFE deliberately uses the SAN URI field because it's a structured, machine-parseable place for a URI identity (and because mTLS peers and policy engines read the SAN, not the CN). Second, the cert is valid for both server *and* client auth (it's used on both ends of mTLS) and is **short-lived** — that `Not After` an hour out is the rotation story from §4. When you write an OPA policy keyed on `spiffe://shop/ns/shop/sa/cart`, you're matching exactly this SAN value, extracted from the *validated* peer cert — which is why it's unforgeable: an attacker can't produce a cert with that SAN signed by your trust domain's CA.

### 2.5 Trust domains and federation

The **trust domain** (`shop` in `spiffe://shop/...`) is the identity boundary, and it matters more than it first appears:

- **Within a trust domain**, all SVIDs are signed by the same CA, so any workload can validate any other's SVID against the one trust bundle. This is your "one mesh, one identity space."
- **Across trust domains**, SVIDs are *not* trusted by default. A workload in trust domain `shop` will *reject* an SVID from trust domain `evil` (or even a legitimately-different `partner` domain), because it doesn't have that domain's CA in its trust bundle. This is a *feature*: it keeps two independent systems from accidentally (or maliciously) authenticating each other's workloads.
- **Federation** is the explicit, deliberate act of trusting *another* domain: the two domains exchange trust bundles, so each can validate the other's SVIDs. A workload in `shop` can then authenticate a workload in `partner` — but only because you *chose* to federate, and only for the domains you federated.

This is directly relevant to the multi-region cart. If you run the two regions in the *same* trust domain (simplest), cross-region cart-to-cart sync is just same-domain mTLS. If you run them as *separate* trust domains (more isolation — a compromise of one region's CA doesn't mint identities valid in the other), you *federate* them and authorize the cross-region call by the *remote* domain's SPIFFE identity. The stretch goal has you do exactly this — federate two SPIRE deployments and authorize across the boundary — which is the genuine multi-region zero-trust story and a real design decision (one trust domain for simplicity vs two for blast-radius isolation).

---

## 3. SPIRE: the runtime that issues identity from attestation

SPIFFE says *what* an identity is; **SPIRE** is the reference implementation that *issues* it. The hard problem SPIRE solves is the one that makes zero trust actually work: **how do you give a workload an SVID without first giving it a secret to authenticate with?** (If you have to hand the workload a credential to prove it deserves a credential, you've just moved the secret-distribution problem, not solved it.) SPIRE's answer is **attestation**: prove what a workload *is* by *inspecting it*, not by what secret it holds.

### 3.1 The two components

- **SPIRE server** — the trust domain's **signing authority**. It holds the CA, issues and rotates SVIDs, and stores the **registration entries** (the rules mapping "a workload with these properties" to "this SPIFFE ID"). One logical server (HA in production) per trust domain.
- **SPIRE agent** — runs on **every node** (a DaemonSet). It does two jobs: it **attests its node** to the server (proving which node it is), and it **attests local workloads** and serves them SVIDs over the **Workload API** (a local Unix socket). The agent is the bridge between the server's authority and the workloads on its node.

### 3.2 Node attestation — proving the node

Before an agent can get SVIDs for workloads, it must prove *which node it is* to the server. This is **node attestation**, and it uses a **node attestor** appropriate to the environment:

- On Kubernetes, the `k8s_psat` attestor has the agent present a **projected service account token** that the server validates against the Kubernetes API — proving the agent really is running in this cluster on this node.
- On AWS, the attestor uses the EC2 instance identity document; on GCP, the instance metadata; and so on.

The point: the node proves itself with a credential *the platform already vouches for* (the cloud's instance identity, Kubernetes' own attestation of its nodes), not a secret you distributed. The platform is the root of the bootstrap.

### 3.3 Workload attestation — proving the workload, with no secret

Once the agent's node is attested, a workload on that node calls the **Workload API** (the local socket) and asks "who am I?" The agent performs **workload attestation**: it inspects the *calling process* to determine its identity — *without the workload presenting any secret*. The attestors look at:

- the process's **Kubernetes metadata** (which pod, which namespace, which service account — obtained by the agent querying the kubelet about the caller),
- the process's **Unix attributes** (uid, gid, path),
- other selectors depending on the attestor.

The agent matches those attested properties against the **registration entries** ("a workload with service account `cart` in namespace `shop` → SPIFFE ID `spiffe://shop/ns/shop/sa/cart`") and, if it matches, hands the workload its SVID.

```
   workload attestation — no secret held by the workload
   cart pod ── calls ──> Workload API socket (local) ── SPIRE agent
                                                          │ inspects the caller:
                                                          │   pod=cart-xyz, ns=shop, sa=cart
                                                          │ matches registration entry
                                                          ▼
                          hands back: SVID for spiffe://shop/ns/shop/sa/cart
   (the workload proved WHAT IT IS by being inspected, not by holding a credential)
```

The **registration entry** is the rule that drives this match. You create it once, on the SPIRE server:

```bash
spire-server entry create \
  -spiffeID spiffe://shop/ns/shop/sa/cart \      # the identity to issue
  -parentID spiffe://shop/spire/agent/...  \     # which agent(s) may issue it
  -selector k8s:ns:shop \                        # ATTESTATION CRITERIA:
  -selector k8s:sa:cart                          #   must be ns=shop AND sa=cart
```

The **selectors** are the heart of the security model: a workload gets `spiffe://shop/ns/shop/sa/cart` *only if* the agent attests it genuinely runs in namespace `shop` under service account `cart`. A pod that *claims* to be cart but runs under a different service account does *not* match these selectors, so it cannot obtain cart's identity — it can only get whatever its *own* attested identity entitles it to. This is why **service-account hygiene is a security control, not a formality**: if `cart` and `frontend` shared a service account, their selectors would be identical and the mesh couldn't tell them apart, so an authorization rule naming "cart" would also admit "frontend." One service, one service account, is what makes the identity (and the authorization built on it) actually mean what you think.

### 3.4 No secret zero — the property that matters

Here is the deep win, and the reason SPIFFE/SPIRE is the right primitive:

> **The workload never *holds* a long-lived credential to be stolen. It proves *what it is* (attestation, done by inspecting it) and is *handed* a short-lived SVID over a local socket. There is no "secret zero" — no bootstrap credential sitting on disk or in an env var that, if leaked, compromises the identity.**

Contrast the old model: you mount a long-lived API key or a static cert into the pod (in a Secret, an env var, a file). That credential is now a thing an attacker who reads the pod's filesystem, dumps its env, or exfiltrates the Secret can *steal* and *replay* — and because it's long-lived, the theft is durable. SPIFFE/SPIRE eliminates that: there's nothing to steal, because the workload's "proof" is *being the workload* (its attested kubelet/uid identity), which an attacker on a *different* workload can't fake. The SVID it receives is short-lived (§4), so even capturing it in flight buys minutes, not forever. **No secret zero** is the single biggest security improvement of this model, and it's why "just use SPIFFE" is the right answer to "how do we identify workloads" in 2026.

### 3.5 The bootstrapping problem, solved by a chain of attestation

It's worth dwelling on *why* "no secret zero" is hard to achieve and how SPIRE pulls it off, because it's the crux of the whole design. The bootstrapping problem is circular: to *get* a credential securely, you usually have to *prove* you deserve it, which usually requires... a credential. Distributing that first credential (the "secret zero") securely is the unsolved-by-secrets problem — wherever you put it (a Secret, an image, an env var), it's a thing that can leak.

SPIRE breaks the circle with a **chain of attestation rooted in the platform**:

1. The **node** proves itself using something the *platform already vouches for* — on Kubernetes, a projected service account token the API server will validate; on a cloud, the instance identity document the cloud signs. SPIRE didn't distribute this; the platform did, as part of running the node. So the *root* of trust is the infrastructure's own attestation, not a secret you placed.
2. The **agent** (now node-attested) is trusted by the server to attest *workloads* on its node.
3. The **workload** proves itself to the agent by being *inspectable* (its kubelet metadata, its uid) — properties an attacker on a different workload can't fake, and again *not a secret the workload holds*.

At no point did anyone distribute a long-lived secret. The trust flows from the platform's built-in attestation (node) down through the agent to the workload, and each link is "prove what you *are*," never "present a secret you *hold*." That chain is the technical achievement, and it's why SPIFFE/SPIRE can give every workload an identity with genuinely no secret zero — something secret-distribution schemes (Vault with a bootstrap token, mounted Secrets) can approximate but never fully achieve, because they always have *some* first credential to protect.

### 3.6 Why "no secret zero" matters for the breach story

Connect it to the threat model from §1. In a perimeter-trust + mounted-secrets world, a single compromised pod is catastrophic *twice over*: the attacker is "inside the trusted network" *and* they can read the long-lived secrets mounted in that pod (and often, via a shared Secret or an over-broad service account, secrets that unlock *other* services). The mounted secret is a key that opens more doors than the one pod. With SPIFFE/SPIRE, a compromised pod yields only *that pod's* short-lived SVID — useless on another workload (it's that pod's identity), useless in minutes (it expires), and not a key to anything the pod itself wasn't already authorized for. The blast radius of a compromise shrinks from "the network plus whatever those secrets unlock" to "this one pod's narrow, expiring identity." That shrinkage is zero trust and no-secret-zero working *together*: identity-not-location confines the attacker to one workload, and no-secret-zero ensures that workload holds nothing worth stealing.

---

## 4. SVID rotation without downtime

### 4.1 Short lifetimes are the feature

SPIRE issues **short-lived SVIDs** — lifetimes measured in minutes to about an hour, not days or years. This is deliberate and it's a *security* feature:

> **A stolen short-lived SVID is worthless almost immediately.** If an attacker somehow captures an SVID, it expires in minutes — far too short to be useful. The shorter the lifetime, the smaller the window a compromised credential is good for. Short lifetimes turn "a leaked credential is a durable compromise" into "a leaked credential is a brief inconvenience."

The cost of short lifetimes — constant re-issuance — is exactly what would make them impractical *if done by hand*. SPIRE makes it free by automating it.

### 4.2 Rotation is automatic and transparent

The Workload API doesn't just hand out an SVID once; it **streams** them. The SPIFFE library (or the mesh's SPIFFE integration) keeps the Workload API connection open, and SPIRE pushes a *fresh* SVID before the current one expires. The application's TLS stack swaps to the new cert under the hood — **no restart, no reconnect storm, no service interruption.** The app code never thinks about certificates; it just keeps serving, and the identity refreshes beneath it.

```
   Workload API stream — SVIDs rotate before expiry, transparently
   t=0    SVID#1 (valid 0–60min)  ── app serves ──
   t=40m  SPIRE pushes SVID#2     ── app's TLS swaps to #2, no restart ──
   t=80m  SPIRE pushes SVID#3     ── ... and so on, forever ──
```

### 4.3 The operational consequence (and the failure mode)

This is why "the certificate expired at 3 a.m." — one of the most common, most avoidable outages there is (Week 8 §5.2) — *cannot happen* with SPIRE: rotation is continuous and automatic, so a cert never silently ages out. The flip side, and a real failure mode you'll name in the runbook: if the **SPIRE server** (the CA) is unavailable for *longer than the SVID lifetime*, agents can't get fresh SVIDs, and as the short-lived ones expire, workloads start failing to authenticate. So **SPIRE server availability is part of your data path's availability** — exactly the istiod-CA lesson from Week 8, now explicit. The runbook line: "SPIRE server down briefly is fine (current SVIDs still valid); SPIRE server down longer than the SVID TTL is an outage as SVIDs expire." This is precisely **certificate expiry**, one of the named failure modes in the capstone runbook and a Week-22 gameday scenario.

### 4.4 The lifetime tradeoff, made operational

How short should SVIDs be? It's a tradeoff, and naming both sides is the senior view:

- **Shorter (minutes):** a stolen SVID is worthless almost immediately (great for security). But the rotation churn is higher — more frequent re-issuance, more load on the SPIRE server, and a *tighter* window before a SPIRE-server outage starts causing expiry failures (if SVIDs live 5 minutes, the server can only be down ~5 minutes before things break).
- **Longer (an hour or a few):** less rotation churn, more slack for a SPIRE-server outage. But a stolen SVID is useful for longer.

The common sweet spot is **on the order of an hour** — short enough that a stolen cert's value is limited, long enough that rotation isn't constant churn and a brief SPIRE-server blip doesn't cause an outage. The key coupling to internalize: **the SVID lifetime *is* your tolerance for SPIRE-server downtime.** If you run very short SVIDs, you *must* run the SPIRE server HA (it can't be down longer than the lifetime); if you can tolerate hour-long SVIDs, you get an hour of slack. This is why the runbook and the HA decision are linked — you choose the lifetime and the server availability *together*, not separately.

### 4.5 Rotation summary

```
SVID ROTATION (the property that designs out cert-expiry outages)
  - SVIDs are SHORT-LIVED (~1h) — a stolen one expires fast
  - the Workload API STREAMS fresh SVIDs before expiry
  - the app's TLS swaps transparently — NO restart, NO reconnect storm
  - => "cert expired at 3am" is impossible... UNLESS:
       SPIRE server down > SVID lifetime -> SVIDs expire -> auth fails
  - therefore: SVID lifetime == your tolerance for SPIRE-server downtime
       -> run SPIRE server HA; monitor it; it's on the data path
```

The whole point: rotation makes the *common* certificate problem (silent expiry) impossible, and converts the *remaining* risk into a single, named, monitorable thing (SPIRE-server availability) that you handle with HA. That's a strictly better place to be than hand-rolled in-app TLS, where every service is its own expiry time bomb.

---

## 5. Why this is the right foundation for the cart

Tie it back to the system. Your multi-region, active-active cart (Weeks 19–20) has `cart`, `inventory`, `payment` workloads across two regions. With SPIFFE/SPIRE:

- **Every workload has a verifiable identity** (`spiffe://shop/ns/shop/sa/cart`, etc.), issued from attestation, with no secret to leak.
- **Every cross-region hop is mutually authenticated** by those identities — `cart` in region A talking to `cart` in region B both present SVIDs, and (with federation) the trust domains validate each other.
- **The identities are the input to authorization** (Lecture 2): an OPA policy that says "only `order` may call `payment`" is meaningful *because* `order` and `payment` are cryptographically verifiable identities, not spoofable IPs.
- **Rotation is automatic**, so the certificate-expiry outage is designed out, and the only remaining cert risk (SPIRE server downtime) is a named, monitored failure mode.

- **Rotation is automatic**, so the certificate-expiry outage is designed out, and the only remaining cert risk (SPIRE server downtime) is a named, monitored failure mode.

The verifiable, attested, short-lived, no-secret-zero identity is the *foundation*; Lecture 2 builds the *authorization* on top of it. Identity answers "who are you" cryptographically; OPA answers "what may you do" — and zero trust requires *both*.

## 5a. The SPIFFE/SPIRE cheat sheet

Keep this open during the exercises:

```
THE STANDARD (SPIFFE)
  SPIFFE ID    spiffe://<trust-domain>/<path>   a NAME for a workload
  SVID         X.509 cert (ID in URI SAN) / JWT  the PROOF of the name
  trust bundle the CA certs that validate SVIDs in a trust domain
  trust domain the identity boundary; cross-domain needs FEDERATION

THE RUNTIME (SPIRE)
  server   the trust domain CA: issues+rotates SVIDs, holds registration entries
  agent    per-node: attests its node, attests workloads, serves the Workload API
  node attestation     prove the NODE (k8s projected token / cloud identity doc)
  workload attestation prove the WORKLOAD by INSPECTING it (ns, sa, uid) — no secret
  registration entry   selectors (k8s:ns / k8s:sa) -> SPIFFE ID to issue

THE PROPERTIES
  no secret zero  the workload holds NO long-lived credential; proves what it IS
  short-lived     SVIDs ~1h; a stolen one expires fast
  auto-rotation   streamed over the Workload API; app's TLS swaps; NO restart
  failure mode    SPIRE server down > SVID lifetime -> SVIDs expire -> auth fails
                  => SVID lifetime == tolerance for SPIRE-server downtime; run HA

THE DISCIPLINE
  one service, one service account (selectors are the security boundary)
  identity is ATTESTED (what you are), not ASSERTED (what you claim) -> unforgeable
```

The one line to carry: **identity is the new perimeter, and SPIFFE/SPIRE gives you that identity from attestation — verifiable, short-lived, and with no secret to steal — which is the only solid foundation an authorization layer can stand on.**

---

## 6. Recap

You should now be able to:

- Explain zero trust ("identity is the perimeter"; no trusted inside; a foothold buys only that workload's identity and authorizations) and why perimeter trust fails on the first breach.
- Describe the SPIFFE ID (`spiffe://trust-domain/path`), the SVID (X.509 with the ID in a URI SAN, or JWT — the *proof*), and the trust bundle (the CA certs that validate SVIDs).
- Describe SPIRE: the server (CA/signing, registration entries), the agent (per-node, attests its node and local workloads, serves the Workload API), node attestation (prove the node via the platform), and workload attestation (prove the workload by inspecting it — kubelet/uid/service-account — no secret held).
- State the **no-secret-zero** property and why it's the key security win: the workload holds no long-lived credential to steal; it proves what it *is* and is handed a short-lived SVID.
- Explain automatic SVID rotation (short lifetimes streamed over the Workload API, transparent to the app), why short lifetimes are a security feature, and why SPIRE-server availability gates SVID rotation (the certificate-expiry failure mode).
- Decode an X.509-SVID and find the SPIFFE ID in the URI SAN, and explain why that (from a validated cert) is unforgeable while an IP/header is not.
- Reason about trust domains and federation: same-domain mTLS within a domain, no trust across domains by default, explicit federation to authorize across — and the one-trust-domain-vs-two decision for the multi-region cart.
- Explain why service-account hygiene (one service, one service account) is a *security control*: the registration-entry selectors are the boundary that makes identity (and the authorization on it) mean what you intend.

The single line to carry into Lecture 2: **everything the authorization layer does rests on the identity being real** — attested (what the workload is), unforgeable (signed by the trust domain CA, in the cert), short-lived (a stolen one expires), and no-secret-zero (nothing to steal). Get the identity right, and OPA has something solid to authorize; get it wrong, and every policy above it is theater.

A closing thought on *why this is worth the operational cost* (a SPIRE server to run HA, agents on every node, registration entries to maintain): you are buying the elimination of an entire class of incidents. No more leaked long-lived secrets. No more 3 a.m. cert-expiry pages. No more "the attacker got one pod and then had the run of the cluster." Those are among the most common and most damaging security incidents there are, and SPIFFE/SPIRE designs them out — converting "a credential leaked, game over" into "a short-lived identity was exposed, useless in minutes." That trade — real operational work for the removal of catastrophic, common failure modes — is why SPIFFE/SPIRE is the 2026 answer to workload identity, and why the capstone requires it.

One more practical note for the exercises: when you deploy SPIRE and an SVID *isn't* issued to a workload, the cause is almost always a **selector mismatch** — the registration entry's `k8s:ns:`/`k8s:sa:` selectors don't match the pod's actual namespace and service account. The diagnostic habit (the zero-trust analogue of `istioctl proxy-config` from Week 8) is:

1. Check the workload's *actual* namespace and service account (`kubectl get pod -o yaml`).
2. Check the registration entry's selectors (`spire-server entry show`).
3. Confirm they match exactly.

A workload with no SVID, or the wrong one, is a selector problem nine times out of ten — and the homework's planted-fault includes exactly this. Train the habit of confirming the *issued* identity (decode the SVID, read the SAN) rather than assuming the registration entry took effect. The recurring lesson, same as the mesh in Week 8: **the issued artifact (the SVID) is ground truth; the config (the registration entry) is only intent, and the gap between them is almost always a selector that didn't match.**

Next up: turning verified identity into authorization — OPA and Rego, request-time authz keyed on SPIFFE identity, admission control, Gatekeeper vs Kyverno, and closing the zero-trust loop with a deliberate violation that gets denied. Continue to [Lecture 2 — OPA, Rego, Policy as Code, and Admission Control](./02-opa-rego-policy-as-code-and-admission-control.md).

---

## References

- *SPIFFE — Overview*: <https://spiffe.io/docs/latest/spiffe-about/overview/>
- *SPIRE — Understanding SPIRE (concepts)*: <https://spiffe.io/docs/latest/spire-about/spire-concepts/>
- *NIST SP 800-207 — Zero Trust Architecture*: <https://csrc.nist.gov/pubs/sp/800/207/final>
- *Google — BeyondCorp*: <https://research.google/pubs/pub43231/>
- *SPIFFE — SVID concepts*: <https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/#spiffe-verifiable-identity-document-svid>
