# Week 9 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 10. Answer key is at the bottom — don't peek.

---

**Q1.** What is the central design bet that distinguishes Linkerd from Istio?

- A) Linkerd uses Envoy; Istio writes its own proxy.
- B) Linkerd built a small, purpose-built Rust micro-proxy that does *only* sidecar work, treating every feature it lacks as one less thing to operate; Istio uses a general-purpose Envoy with the broadest feature set.
- C) Linkerd has no control plane.
- D) Linkerd is closed-source; Istio is open.

---

**Q2.** Why is `linkerd2-proxy` written in Rust, and what does it buy?

- A) Rust is the only language that compiles to Kubernetes.
- B) Memory-safety (no use-after-free/buffer overflows in a component that terminates TLS) plus a small, predictable footprint because it does one job — far less per-pod memory than a general-purpose Envoy.
- C) Rust makes it faster than the kernel.
- D) It's a marketing choice with no technical basis.

---

**Q3.** How does Linkerd's mTLS default differ from Istio's?

- A) Linkerd has no mTLS.
- B) In Linkerd, mTLS between meshed pods is automatic and on by default the moment both ends are meshed — no `PeerAuthentication` to write; Istio's mTLS is available on install but not enforced until you apply a STRICT policy.
- C) Istio's is automatic; Linkerd's requires manual certs.
- D) They're identical.

---

**Q4.** What is Cilium's central architectural answer to the per-pod-proxy question?

- A) Make the sidecar smaller (like Linkerd).
- B) Make the sidecar optional per pod (like Istio ambient).
- C) Eliminate the per-pod proxy for L4: do load balancing, policy, and mTLS in the kernel via eBPF, with a per-node embedded Envoy only for L7.
- D) Use a per-pod Envoy like Istio.

---

**Q5.** In one sentence, what is eBPF and why does it matter for a mesh?

- A) A userspace proxy framework that replaces Envoy.
- B) Sandboxed programs the kernel runs on events (packets, sockets), verified safe before they run — letting load balancing, policy, and connection handling happen in the kernel datapath without bouncing to a userspace proxy.
- C) A Kubernetes CRD for network policy.
- D) A new programming language for writing proxies.

---

**Q6.** In Cilium service mesh, where do L4 and L7 traffic get handled?

- A) Both in a per-pod sidecar.
- B) L4 (+ mTLS) in the kernel via eBPF with no per-pod proxy; L7 (HTTP routing/policy) through a per-node embedded Envoy.
- C) Both in the per-node Envoy.
- D) L4 in userspace, L7 in the kernel.

---

**Q7.** What is a real cost of choosing Cilium as your service mesh?

- A) It has no mTLS.
- B) It's also your CNI (so adopting it for mesh means adopting it for networking — a migration if you're on another CNI), and its L7 mesh feature set is younger than Istio's.
- C) It requires a per-pod sidecar after all.
- D) It can't do network policy.

---

**Q8.** A local Kind benchmark of the three meshes shows Cilium fastest. What does this justify?

- A) Adopt Cilium immediately — it's the fastest.
- B) Nothing on its own — a Kind benchmark is relative (trust ordering/ratios, not absolutes), qualified to one workload; latency is one axis, and if the org needs Istio's L7 or can't change its CNI, the latency win is irrelevant.
- C) That Istio is broken.
- D) That meshes don't add overhead.

---

**Q9.** What does the proxy-memory column in your mesh benchmark reveal?

- A) Nothing useful.
- B) The architecture made visible: Istio's general-purpose Envoy sidecar is heaviest per pod, Linkerd's micro-proxy is a fraction of it, and Cilium's eBPF L4 path has no per-pod proxy memory at all — a multi-gigabyte fleet-wide difference at scale.
- C) Only the control plane's memory.
- D) That all three use the same memory.

---

**Q10.** What are the six axes on which real orgs choose a mesh?

- A) Color, logo, license, language, age, popularity.
- B) Cost (latency/memory), operational complexity, L7 feature depth, mTLS model, multi-cluster story, and ecosystem/maturity.
- C) Only latency and price.
- D) CPU, RAM, disk, network, GPU, and TPU.

---

**Q11.** When is the right answer "no mesh at all"?

- A) Never — every cluster needs a mesh.
- B) When the value of uniform east-west mTLS/telemetry/policy applied without per-team effort doesn't exceed the cost of operating a mesh — e.g., a small/simple system where a gateway plus a shared library suffices.
- C) Only when you can't afford a license.
- D) Only in development.

---

**Q12.** What makes an ADR a *decision* rather than a *preference*?

- A) It's written in a doc instead of said aloud.
- B) It states the context, weighs the options for the *specific* org (with evidence), commits to a choice, names the consequences, AND states the reversal conditions that would make you revisit — committing while staying honest about uncertainty.
- C) It recommends the most popular option.
- D) It avoids committing so it can't be wrong.

---

**Q13.** In a design review, an objection to your mesh choice "has merit." What's the staff-engineer response?

- A) Re-assert your original choice; never concede.
- B) Immediately switch to whatever the objector implied.
- C) Concede the merit explicitly, then either hold your position with evidence ("yes, that's a real cost, and here's why it's still worth it") or change it for a stated reason — merit isn't the same as decisive.
- D) End the meeting.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Linkerd's bet: smallest purpose-built proxy, simplicity as a feature; Istio's: most powerful general-purpose Envoy. (Lecture 1 §1, intro.)
2. **B** — Memory-safety + small predictable footprint from doing one job. (Lecture 1 §1.2.)
3. **B** — Linkerd: automatic, on-by-default mTLS; Istio: available but not enforced until STRICT. (Lecture 1 §2.)
4. **C** — Eliminate the per-pod proxy for L4; kernel/eBPF does it; per-node Envoy for L7. (Lecture 2 §1.2.)
5. **B** — Sandboxed, verified kernel programs on events; kernel-datapath networking without a userspace proxy. (Lecture 2 §1.1.)
6. **B** — L4+mTLS in kernel (no per-pod proxy); L7 via per-node embedded Envoy. (Lecture 2 §1.2.)
7. **B** — Cilium-as-mesh = Cilium-as-CNI (coupling/migration), and a younger L7 story. (Lecture 2 §1.3.)
8. **B** — A relative benchmark on one workload; latency is one axis; fit (L7, CNI) can override it. (Lecture 2 §2.2–2.3, §3.1.)
9. **B** — The architecture as a number: heavy Istio sidecar, light Linkerd, none for Cilium L4. (Lecture 2 §2.3.)
10. **B** — Cost, ops complexity, L7 depth, mTLS model, multi-cluster, maturity. (Lecture 2 §3.1.)
11. **B** — When the mesh's value doesn't exceed its operating cost; small systems → gateway + library. (Lecture 2 §3.2.)
12. **B** — Context, evidence-weighed options, a committed choice, consequences, AND reversal conditions. (Lecture 2 §3.3.)
13. **C** — Concede the merit, then hold-with-evidence or change-for-a-reason; merit ≠ decisive. (Challenge 1.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
