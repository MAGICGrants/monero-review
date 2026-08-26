# Trust boundaries

Where untrusted data enters Monero, and what "untrusted" means at each point.
Use this to answer the reachability question concretely: name the boundary, then
trace the call sequence from it to the changed code.

Verify locations against the checkout — this is a map, not a substitute for
reading the tree. Use the symbol index (`readtags -n <sym>`, `cscope -dL3 <fn>`)
to confirm callers rather than assuming.

## 1. P2P messages — any peer, no authentication

`src/cryptonote_protocol/cryptonote_protocol_handler.inl`

Handlers named `handle_notify_*` and `handle_response_*` receive structures
that a peer fully controls: new blocks, new transactions, fluffy blocks, and
responses to our own object requests. Anyone can connect and send these.

The response handlers are worth particular attention: code often assumes a
response corresponds to what was requested, and a malicious peer is under no
obligation to comply. Mismatched counts, unexpected ordering, and absent
entries are all reachable.

Framing and message dispatch live in
`contrib/epee/include/net/levin_protocol_handler_async.h`.

## 2. RPC — public or admin, and the difference matters

`src/rpc/core_rpc_server.cpp`, handlers named `on_*`

The server distinguishes **restricted** (public, what a remote wallet talks to)
from **unrestricted** (full admin). Check which applies to the handler you are
looking at before claiming remote reach — the gating is in the code, not
inferable from the method name.

A finding reachable only by an unrestricted client is usually not a finding,
because that client is already trusted with far more. A finding on the
restricted surface of a public node is the real thing.

## 3. Deserialization — the widest surface

`src/serialization/`, `contrib/epee/include/serialization/`

Every P2P message, RPC body, and wallet cache passes through here. This is
where attacker-chosen counts meet `resize()` and `reserve()`.

It is also where most memory-safety findings die: the layer imposes limits
before application code runs. See `refutations.md` — trace the field's actual
constraint before reporting.

## 4. Daemon → wallet — the daemon is NOT trusted

`src/wallet/wallet2.cpp`

This boundary is easy to overlook and has repeatedly produced real bugs. A
wallet connecting to a remote node treats that node's responses as untrusted
input. `process_parsed_blocks`, `process_new_transaction`, and
`process_new_blockchain_entry` all parse data a malicious or compromised daemon
chose.

The threat model that matters: a user runs a GUI wallet or `wallet-rpc` against
a public remote node. Anything the node can say that corrupts wallet memory,
crashes it, or induces a wrong spend is in scope, and severity is high because
the wallet holds keys.

`import_key_images` deserves the same treatment — key-image blobs arrive from
outside and are parsed into wallet state.

## 5. Wallet cache and key files

Opening a wallet parses an on-disk cache. "The user opened a file they were
given" is a realistic threat model for custodial and multi-user setups. Treat
cache parsing as untrusted input, not as trusted local state.

## 6. Consensus validation

`src/cryptonote_core/blockchain.cpp`, `tx_pool.cpp`, `src/ringct/`,
`src/crypto/`

Block and transaction acceptance. Bugs here are consensus-critical by
definition: the question is not just "does it crash" but "would a node running
this code reach a different verdict than the rest of the network on the same
input".

Fork gating lives in `src/hardforks/hardforks.cpp` and the `HF_VERSION_*`
constants. Any behaviour change must be gated to the correct version, and you
should ask explicitly whether an ungated change makes old and new nodes
disagree.

## 7. Build and CI

`CMakeLists.txt` files, `.github/workflows/`, `contrib/depends/`

Not consensus code, but a supply-chain surface. A change that alters what gets
compiled in, disables a hardening flag, changes a dependency source or pinned
hash, or weakens a release workflow is worth reporting even though it is not a
memory-safety bug. Removal of a hardening flag (`-D_FORTIFY_SOURCE`, stack
protector, RELRO, PIE) is a genuine finding.

## Severity anchoring by boundary

| Reached from | Typical ceiling |
| --- | --- |
| Consensus validation, any divergence | CRITICAL |
| P2P, unauthenticated, memory corruption | CRITICAL |
| Malicious daemon → wallet memory corruption | CRITICAL (keys are present) |
| P2P or restricted RPC, crash or OOM | HIGH |
| Malicious daemon → wallet crash | HIGH |
| Privacy break that links or deanonymises | HIGH |
| Requires non-default option or unusual position | MEDIUM |
| Unrestricted-RPC-only, or test-only | LOW, usually not reportable |
