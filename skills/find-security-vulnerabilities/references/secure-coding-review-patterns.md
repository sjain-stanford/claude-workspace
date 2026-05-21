# Secure Coding Review Patterns

Use these patterns to turn a broad security review into concrete code questions. They are especially useful for native code, firmware, drivers, privileged services, parsers, IPC, shared memory, and mailbox-style command handlers.

## Threat Modeling Prompts

- Identify critical assets: secrets, keys, credentials, protected records, firmware/software images, security state, admin actions, tenant data, debug unlock state, and build or release authority.
- Identify critical responsibilities: guarantees the system must preserve, such as secure boot, anti-rollback, update integrity, access to sensitive resources, authentication flows, or configuration authorization.
- Map each asset to the security property it needs: confidentiality, integrity, availability, authentication, authorization, or abuse resistance.
- Enumerate attack surfaces by attacker proximity:
  - Local: APIs, IPC, system calls, mailboxes, shared memory, MMIO, registers, files, sockets, plugins, and CLI inputs.
  - Remote: network protocols, web APIs, webhooks, radio/baseband interfaces, update services, and package fetchers.
  - Physical: USB, serial buses, flash/storage media, debug ports, removable media, and sensors.
- Treat data crossing a trust boundary as attacker-controlled until validated. Prioritize interfaces where a lower-privilege actor can influence a higher-privilege component.

## Memory Safety Review

- Separate memory corruption from memory exposure. Corruption threatens integrity and often control flow; exposure threatens confidentiality through unintended reads or returned data.
- For every attacker-controlled size, count, length, index, offset, and enum:
  - Check both minimum and maximum bounds.
  - Check exact-size requirements when the protocol expects a fixed structure.
  - Check integer overflow before `base + size`, `offset + len`, `count * elem_size`, alignment, or truncating casts.
  - Check signed/unsigned mixing, implicit narrowing, off-by-one conditions, and unit mismatches.
- For every attacker-controlled pointer, address, file offset, slice, span, or buffer reference:
  - Validate the full range, not just the start address.
  - Reject wraparound by verifying the end is greater than or equal to the start before comparing limits.
  - Verify the range stays inside the intended low-privilege or untrusted memory region and does not overlap sensitive memory.
  - Revalidate after address translation, mapping, canonicalization, or symlink resolution.
- For copies into fixed buffers, verify the destination capacity before copying. For copies out to an attacker-supplied destination, verify both the destination range and that the requested length cannot exceed intended data.
- For strings, verify termination, encoding, maximum length, and whether APIs count bytes, characters, or elements.
- For structs crossing trust boundaries, initialize the entire object before populating fields so padding and stale stack/heap bytes cannot leak.
- For parsers and pre-authentication loaders, validate headers before using fields such as load address, body size, offset, entry point, compression size, and section count. Authenticate before trusting mutable content, and execute or consume the same validated bytes.

## Logic Error Review

- Look for API misuse where argument order or semantics are easy to swap, especially `memset`, copy routines, allocation, cryptographic APIs, path APIs, and permission helpers.
- Check that every allocation, parse, read, write, map, lock, verify, and crypto operation handles failure before dependent data is used.
- Look for gaps in conditional logic, especially `<` paired with `>` that misses equality, or checks that allow zero-length, exact-header-only, negative, NaN, null, empty, duplicate, or unknown enum cases.
- Reject unsafe reliance on debug-only assertions for attacker-controlled input. Release builds must use explicit runtime validation and safe error handling.
- Treat uninitialized locals, partially initialized structs, stale globals, and reused buffers as possible control-flow bugs or data leaks.
- Check that error paths do not leave privileged state updated, locks held, temporary permissions granted, partially written files, or inconsistent authentication state.

## Race And TOCTOU Review

- Find check-then-use patterns where an attacker can change the checked object before use: files, symlinks, flash/storage, shared memory, registers, MMIO, IPC payloads, database rows, cache entries, and external service state.
- Read attacker-controlled registers or shared-memory metadata once into local variables, validate the local copy, and use that same local copy.
- Copy shared payloads into private memory before parsing when the sender can mutate memory concurrently.
- Validate again after mapping, opening, resolving, locking, or fetching if the operation can change the referenced object.
- For verified firmware, packages, archives, or config, consume the same bytes that were verified. Avoid validating one copy and executing, loading, or installing another.
- Prefer atomic open/use primitives, file descriptors over paths, locks with clear ownership, immutable snapshots, idempotency keys, transactions, and version checks.

## Privilege Management Review

- Separate authentication from authorization. A request can prove identity and still lack permission for the action.
- Require unguessable session or capability tokens for authenticated state; do not rely only on user IDs, names, client-side flags, or "currently logged in" globals.
- Check authorization at the point of use for every sensitive action, object, tenant, command, and target resource.
- Look for confused deputy paths where a lower-privilege client can make a higher-privilege service read, write, map, delete, sign, decrypt, fetch, or execute something it could not access directly.
- Validate user-provided addresses, paths, object IDs, handles, file descriptors, URLs, and resource names against the caller's authority, not only against syntactic validity.
- Prefer privilege minimization and separation: split high-risk operations into smaller components, drop privileges early, use least-privilege tokens, and constrain tool or plugin capabilities.

## Mitigation Review

- First prevent the bug with strict validation, exact-size checks, safe APIs, local snapshots, complete initialization, and explicit authorization.
- Then reduce impact with sandboxing, memory-safe languages or wrappers, ASLR/DEP/CFI/stack canaries, seccomp, container isolation, read-only mounts, resource limits, and least privilege.
- Then block or slow exploitation with rate limits, logging, anomaly detection, defense in depth, key rotation, replay protection, and requiring attackers to chain independent flaws.
- Do not rely on mitigations to dismiss a confirmed memory corruption, trust-boundary bypass, or authorization failure unless the mitigation is verified on the affected build and deployment path.
