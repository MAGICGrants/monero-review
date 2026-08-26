# Refutation patterns

Candidate findings in this codebase die for a small number of recurring
reasons. Check the relevant ones before reporting anything — each has produced
false positives in past review work.

State in the report which of these you checked. "I confirmed the serializer
does not cap this" is evidence; silence is not.

## The serializer already bounds it

Monero's serialization layer imposes limits before application code ever sees
a value, so an "attacker-controlled count drives a huge allocation" finding is
often unreachable in practice.

Before reporting one, read the actual serializer for the type — in
`src/serialization/` and `contrib/epee/include/serialization/` — and find the
constraint on the field. Look for `FIELD`/`VARINT_FIELD` macros with explicit
checks, `*_MAX`/`*_LIMIT` constants, and any `if (n > ...) return false` in the
read path.

This is the most common way a genuine memory-safety *primitive* turns out to
have no reachable path. The primitive being real is not the finding; reaching
it is.

## Proof-dimension bugs in RingCT and Bulletproofs+

Indexing and buffer-sizing bugs in `src/ringct/` verification are frequently
fenced off because the proof's dimensions are validated during deserialization,
long before the arithmetic that would overflow. Trace the dimension field from
the wire to the arithmetic and identify every check on the way. If the only
way to reach the bug is a proof shape the deserializer rejects, it is at most a
hardening note.

## The config option defaults to off

A path reachable only when a non-default option is enabled is at most MEDIUM,
and usually LOW. Find the default — in the option's declaration, not in
documentation — and state it. Wallet and daemon both have options that sound
enabled but are not.

## The RPC handler is restricted

`src/rpc/core_rpc_server.cpp` distinguishes restricted (public) from
unrestricted (full-admin) clients. A handler reachable only by an unrestricted
client is generally not a finding, because that client can already do far worse
by design. Confirm the handler's actual gating before claiming remote reach —
do not assume from the method name.

## Boost already throws

`boost::regex` has a complexity limit and throws when a match exceeds it, and
callers in this codebase generally catch. Catastrophic-backtracking findings
against `boost::regex` are refuted by default: to report one you must show both
that the limit does not trigger and that the throw is not caught.

Similar shape for `boost::asio` timeouts and Boost container bounds — check for
the library-level guard before assuming application code is the only defence.

## An existing assertion covers it

Look for `CHECK_AND_ASSERT_MES`, `CHECK_AND_ASSERT_THROW_MES`,
`THROW_WALLET_EXCEPTION_IF`, and plain `if (...) return false` in the call
chain. A macro two frames up often makes the local-looking bug unreachable.
Note that some of these compile out or only log depending on build flags — if
your refutation depends on an assertion, say which kind it is.

## The caller already validated it

C++ makes this easy to miss: the dangerous function is a private helper with
one or two callers that both check the precondition. Use the symbol index
(`cscope -dL3 <fn>`) to enumerate callers rather than assuming, then read each
one. A helper with no external caller is not remotely reachable.

## The type is wide enough

Before claiming integer overflow, check the actual types involved, including
any promotion. `size_t` on 64-bit does not overflow at values an attacker can
realistically supply through a size-limited message.

## The race is actually serialized

Before reporting concurrent access, establish that two threads genuinely reach
the state at once. A great many candidates turn out to be sequenced by an
existing lock or by the refresh cycle. This matters beyond a yes/no: if an
operation is serialized, an attacker-influenced write to it is *deterministic*
rather than racy, which is a different (often stronger, sometimes weaker) claim
than the one the first pass made. Name the lock, or name the two call sites that
run concurrently.

## The divergent path does not ship

For code with multiple implementations of the same computation — interpreter
versus JIT, with and without hardware acceleration, per architecture — a
difference between paths is only a consensus break if both paths run on real
nodes. Establish which are built and used in production before assigning
severity. A divergence on an architecture or build option nobody ships is a LOW.

## The construction already constrains it

In proof systems, an operation that looks wrong in isolation is often
constrained by the surrounding protocol. Divisor arithmetic modulo the field
prime, and point-versus-negation handling, have both repeatedly looked like
breaks and turned out to be fine once the protocol's own constraints were taken
into account. Read the construction, not just the function.

## It is test-only code

Changes under `tests/` do not ship. They matter only if they also modify
non-test code, or if they weaken a fuzz harness in a way that would hide future
bugs — the latter is worth a LOW note, not a vulnerability report.

---

None of this means "do not report". It means the report must name the guard you
checked and explain why it does not hold. A finding that survives an honest
attempt at each applicable refutation above is worth a security engineer's
time. One that has not been through this is not.
