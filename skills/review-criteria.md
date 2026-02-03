# Shared Review Criteria

Common review checklist and standards shared across code review skills.

## Review Checklist

Evaluate code changes against these criteria in order of importance:

### Critical Issues
- Security vulnerabilities (injection, XSS, buffer overflows)
- Data corruption or loss potential
- Breaking changes to public API without migration path
- Memory leaks or resource management bugs
- Race conditions or deadlocks

### Major Issues
- **Correctness**: Does the implementation match the stated intent?
- **Test coverage**: Are there unit and/or integration tests for new/modified code?
- **API consistency**: If touching user-facing API (e.g., `fusilli::Graph`), ensure consistency with cudnn-frontend / hipdnn API
- **Error handling**: Are errors properly propagated and handled?
- **No Exceptions**: We follow the no-exception policy from LLVM, so flag any uses of throw/catch exceptions

### Minor Issues
- This includes code style or organization issues - generally nit picks but important for code readability and maintainability

### General Recommendations
- Follow DRY (don't repeat yourself), YAGNI (you aren't gonna need it), KISS (keep it simple, stupid)
- If extending or bug-fixing existing code, use the style already in place to maintain uniformity
- Reference LLVM coding standards (`skills/llvm-coding-standards.md`) to ensure new code conforms to it

## Code Standards

Reference `skills/llvm-coding-standards.md` for detailed standards. Key checks:

- **Braces**: Omit braces when body is a single simple statement with no preceding comment; use braces for multi-statement, commented, or nested blocks
- **Include order**: Main module header first, then local/private, then project headers, then system headers (each category sorted lexicographically by full path)
- **Early exits and continue**: Prefer early returns to reduce nesting
- **Don't use else after return**: Reduces indentation
- **Prefer preincrement**: Use `++i` over `i++`
- **Auto usage**: Use `auto` only when type is obvious; prefer `auto &` for values, `auto *` for pointers
- **Range-based for loops**: Use wherever possible
- **Assertions**: Use `assert` liberally with descriptive messages
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

## Output Format

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
