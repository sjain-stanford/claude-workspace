# Shared Review Criteria

Common review checklist and standards shared across code review skills.

## Review Checklist

Evaluate code changes against these criteria:

### General Recommendations
- Follow DRY (don't repeat yourself), YAGNI (you aren't gonna need it), KISS (keep it simple, stupid)
- If extending or bug-fixing existing code, use the style already in place to maintain uniformity
- Read the target repository's `AGENTS.md`, `CONTRIBUTING.md`, and applicable
  design/style docs. Project-specific rules override this shared checklist.
- Reference LLVM coding standards (`skills/llvm-coding-standards.md`) only when
  the target project adopts them; rocjitsu's own `CONTRIBUTING.md` and
  `docs/style.md` are authoritative for rocjitsu.
- Always accompany each flagged issue with the proposed fix or refactoring suggestion, inline with the issue
- Only flag actual issues that need to be addressed; do not include observations about correct behavior or analysis notes in the "Issues" sections

### Evidence Standard for Findings

- Independently validate every finding before including it in a review. Agent
  output is a lead, not evidence: trace the relevant code path at the reviewed
  commit and confirm that the claimed behavior is reachable.
- Prefer a minimal reproducer or focused test. When that is impractical,
  corroborate the claim with authoritative documentation and a second
  independent source of evidence. Record contradictions instead of selecting
  whichever source supports the finding.
- Do not infer runtime semantics from names, comments, generated-code shape, a
  shared encoding field, assembler acceptance, or compiler instruction
  selection alone. These establish different facts and are not interchangeable.
  For ISA findings, distinguish syntax legality, encodability, modifier
  applicability, compiler lowering, specified semantics, and observed hardware
  behavior.
- If authoritative sources or observations disagree, or the behavior cannot be
  verified, present it as an explicit question or omit it. Do not assign a
  severity or high-confidence label to an unresolved hypothesis.
- Before publishing or forwarding findings from another agent, the active
  reviewer or curator owns their accuracy and must repeat this validation.

### Critical Issues
- Security vulnerabilities (injection, XSS, buffer overflows)
- Data corruption or loss potential
- Breaking changes to public API without migration path
- Memory leaks or resource management bugs
- Race conditions or deadlocks

### Major Issues
- **Correctness**: Does the implementation match the stated intent?
- **Test coverage**: Are there unit and/or integration tests for new/modified code?
- **Error handling**: Are errors properly propagated and handled?
- **Project error model**: Enforce the target project's policy. In rocjitsu,
  expected failures use `Result`/`FailureOr<T>` and optional diagnostics;
  exceptions are reserved for unrecoverable initialization, configuration, or
  execution failures and should not enter simulation hot paths.

### Minor Issues
- Report minor issues such as code style or code organization issues
- These are generally nit picks but important for code readability and maintainability

## Code Standards

Use the target project's documented style. The following are fallback checks,
not grounds for overriding explicit project conventions:
- **Braces**: Omit braces when body is a single simple statement with no preceding comment; use braces for multi-statement, commented, or nested blocks
- **Early exits and continue**: Prefer early returns to reduce nesting
- **Don't use else after return**: Reduces indentation
- **Prefer preincrement**: Use `++i` over `i++`
- **Auto usage**: Use `auto` only when type is obvious; prefer `auto &` for values, `auto *` for pointers
- **Range-based for loops**: Use wherever possible
- **Assertions**: Use `assert` liberally with descriptive messages
- **Include order**: Follow the local formatter and neighboring files; prefer
  stable, grouped, lexicographical ordering when the project does not specify it.
- **Comments**: Write as English prose with proper capitalization and punctuation (start uppercase, end with period)

## Special Checks

### Copyright Headers
For new files, verify copyright year is the current year (not copied from older files).

### TODO Comments
Ensure TODOs follow the convention:
- Same repo: `TODO(#issue-number)`
- External repo: `TODO(org/repo#issue-number)`

### Modern C++ Features
Look for opportunities to simplify verbose code by leveraging C++17 or C++20 features when possible.

### rocjitsu Checks

When reviewing `rocm-systems/emulation/rocjitsu`, also load
`skills/rocjitsu-project/SKILL.md` and inspect the relevant project docs.

- Generated ISA decoders, encoders, execute bodies, legalization tables, and
  encoding translators must be changed through `amdisa`, not edited directly.
- ISA changes should cover affected architecture gates, encodings, operand
  widths/modifiers, EXEC/lane masks, and scalar/SIMD behavior.
- DBT/DBI changes should preserve branches, relocations, symbols, descriptors,
  scratch/LDS, liveness/implicit operands, and fail-closed diagnostics.
- KFD/interposer/daemon changes should preserve ioctl ABI behavior, errno, file
  descriptors, mapping and process lifecycle, cleanup, and runtime isolation.
- Do not classify every TSan report at shared-memory aliases as a product race;
  first determine whether it is the documented HSA/doorbell happens-before
  modeling gap. Do not use that limitation to dismiss unrelated races.
- Performance claims require the protocol in `docs/benchmarking.md`.

### Fusilli Checks

Only for explicit Fusilli reviews, retain the historical compatibility checks
against cuDNN frontend/hipDNN, Torch-MLIR ASM, IREE C APIs, and the public
`<fusilli.h>` include bundle.

## Output Format

**Line Number Convention**: Reference file-relative source locations (for
example, `emulation/rocjitsu/lib/.../file.cpp:163`), not diff-relative line
numbers, so findings are directly navigable.

Report issues in decreasing order of severity:

```markdown
## <Review-Type>: <title>

**Source**: <URL or branch info>
**Author**: <author>
**Branch**: <head> -> <base>

### Summary
<Brief summary of what the changes do>

### Critical Issues
<List or "None">

### Major Issues
<List or "None">

### Minor Issues
<List or "None">

### Recommendations
<Suggestions for improvement>

### Verdict
<APPROVE / REQUEST_CHANGES / COMMENT>
```
