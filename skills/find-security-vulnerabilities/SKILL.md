---
name: find-security-vulnerabilities
description: Find and assess exploitable security vulnerabilities in source projects. Use when auditing code, dependencies, configuration, CI/CD, infrastructure-as-code, auth, data handling, web/API surfaces, native memory safety, or AI-agent/tool integrations for malicious-actor exploitability; produce evidence, severity, impact, and remediation while avoiding weaponized exploitation guidance.
---

# Find Security Vulnerabilities

## Overview

Use this skill to perform defensive security review of projects the user owns or is authorized to test. Focus on real exploitability, clear evidence, and fixes that maintainers can act on. Do not provide instructions, payloads, or operational steps that would enable unauthorized compromise of live third-party systems.

## Operating Boundaries

- Confirm the target is a local project, user-owned repository, or explicitly authorized assessment. If the user asks to attack a live third-party target, redirect to passive review of provided artifacts or high-level defensive guidance.
- Prefer static review, local tests, and harmless proof artifacts. Avoid live exploitation, persistence, stealth, credential use, data exfiltration, destructive actions, or public exploit automation.
- Show enough evidence for maintainers to reproduce and fix the issue, but omit weaponized payloads, bypass recipes, or chained attack instructions unless the user is clearly working in an authorized local lab and needs a minimal safe reproducer.
- Preserve secrets and sensitive data. If secrets are discovered, report the file path and secret type, redact values, and recommend rotation.

## Review Workflow

1. Scope the project:
   - Identify languages, frameworks, dependency managers, deployment targets, and exposed surfaces.
   - Locate routes/controllers, RPC handlers, CLIs, background jobs, auth middleware, data models, migrations, config files, CI workflows, Docker/Kubernetes/Terraform, and environment examples.
   - Read `README`, docs, threat-model notes, security policy, and test setup before running tools.

2. Build a threat model:
   - Name critical assets and critical responsibilities: credentials, user data, money movement, admin actions, tenant boundaries, secure boot or update guarantees, model/tool access, and build/release credentials.
   - Classify the required security properties: confidentiality, integrity, availability, authentication, authorization, non-repudiation, or abuse resistance.
   - Map trust boundaries: browser to API, public API to internal services, user uploads to storage, CI to production, plugin/tool calls to host capabilities.
   - List attacker-controlled inputs and raceable shared resources: request params, headers, cookies, webhooks, files, archives, URLs, templates, prompts, serialized data, config, dependency metadata, shared memory, registers, storage, and filesystem paths.

3. Search deliberately:
   - Use `rg` to find risky sinks, missing authorization, secret material, unsafe deserialization, shell/database/template execution, file/path handling, SSRF-capable fetches, CORS/CSRF/session settings, CI secret exposure, unsafe assertions, memory-copy boundaries, and unchecked pointer/size arithmetic.
   - Use language-native scanners or package-audit tools when available, but verify findings manually before reporting.
   - Read call paths around each hit instead of reporting keyword matches.

   Useful starting searches:

   ```bash
   rg -n "TODO|FIXME|SECURITY|auth|authorize|permission|isAdmin|admin" .
   rg -n "eval|exec|spawn|system|popen|subprocess|shell=True|child_process|innerHTML|dangerouslySetInnerHTML|pickle|yaml.load|jwt.decode|assert|ASSERT" .
   rg -n "memcpy|memmove|memset|strcpy|strncpy|strcat|sprintf|snprintf|malloc|free|realloc|new\\[|delete\\[|sizeof|uintptr|uint32|size_t" .
   rg -n "password|passwd|secret|token|api[_-]?key|private[_-]?key|BEGIN (RSA|OPENSSH|PRIVATE) KEY|AWS_" .
   rg --files | rg "(package-lock.json|pnpm-lock.yaml|yarn.lock|requirements.*\\.txt|poetry.lock|Pipfile.lock|Cargo.lock|go.sum|pom.xml|build.gradle|Dockerfile|docker-compose|\\.github/workflows|terraform|k8s|helm)"
   ```

4. Establish exploitability:
   - Require a reachable entry point, attacker influence over data or state, a missing or weak control, and meaningful impact.
   - Trace the vulnerable data flow from source to sink with file and line references.
   - For trust-boundary code, check both directions: malformed input entering the component and unintended data leaving it.
   - Treat memory corruption as exploitable until the code path, platform mitigations, and privilege boundary prove otherwise.
   - Prefer local unit/integration tests that demonstrate the bug with harmless values.
   - Distinguish confirmed findings from hypotheses. Do not inflate severity for unreachable or already-mitigated code.

5. Recommend fixes:
   - Propose the smallest robust fix that matches project patterns.
   - Add or suggest regression tests for confirmed findings.
   - Call out operational follow-up: secret rotation, dependency upgrade, migration, log scrubbing, config change, or deployment action.

## Vulnerability Checklist

Load `references/vulnerability-review-checklist.md` when the project surface is broad, the first pass is inconclusive, or a category-specific review would help. Use it as a prompt for investigation, not as a substitute for tracing real code paths.

Load `references/secure-coding-review-patterns.md` when reviewing native code, firmware, drivers, parsers, privileged services, IPC/mailbox-style interfaces, or code that crosses explicit trust boundaries. It contains distilled secure-coding patterns from the local training PDF without reproducing the source material.

## Reporting Format

Lead with findings ordered by severity. For each confirmed issue, include:

- Severity and category, preferably with CWE/OWASP mapping when obvious.
- Affected files and lines.
- Attack preconditions and exploit path at a safe level of detail.
- Impact on confidentiality, integrity, availability, tenant isolation, or supply chain.
- Evidence from code review or a harmless local reproducer.
- Concrete remediation and regression test guidance.

If no confirmed vulnerabilities are found, state that clearly and list the highest-risk areas reviewed plus any residual gaps, such as unaudited dependencies, unrun tests, missing runtime configuration, or unavailable infrastructure context.
