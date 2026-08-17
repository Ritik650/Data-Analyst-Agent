# Security Policy

## Scope

This project executes **LLM-generated Python code** in a sandboxed subprocess, accepts uploaded datasets, and calls an external LLM API. This is inherently higher-risk than a typical web service, so security reports are especially welcome for:

- **Sandbox escapes** ([sandbox/](sandbox)) — any way to break out of the rlimit/no-network/import-allowlist boundaries
- **File access beyond the scoped temp directory** — see the *known limitation* already documented below before reporting the general "shared OS user" gap
- **Secret leakage** — `GEMINI_API_KEY`, `REDIS_URL`, or job data appearing somewhere it shouldn't (logs, error messages, report output)
- **Job/report isolation** — one job's data or report becoming visible to another job/user via Redis

## Already-known limitation (please don't re-report this specific gap)

The README's [Security section](README.md#security-the-sandbox-tradeoff-stated-honestly) documents an accepted, stated tradeoff: subprocess sandboxing shares the OS user with the worker, so a sufficiently determined adversary using library-internal file loaders (e.g. `pd.read_csv("/etc/passwd")`) can read files readable by that user. This is a known gap, not an oversight — the fix (Docker-per-run or gVisor/Firecracker isolation) is called out as future work.

**What *is* worth reporting:** a way to exploit that gap for something worse than local file read (e.g., reaching the host network despite the socket monkeypatch, escaping the rlimit/timeout bounds, or exfiltrating another job's data via Redis).

## Supported Versions

Only the latest commit on `main` is supported.

| Version | Supported |
|---|---|
| `main` (latest) | ✅ |
| Older commits | ❌ |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities, especially sandbox escapes.

Report privately via one of:
- GitHub's [private vulnerability reporting](https://github.com/Ritik650/Data-Analyst-Agent/security/advisories/new) (Security tab → Report a vulnerability)
- Email: ry9812262@gmail.com

Please include a minimal reproduction (ideally a specific `problem` + dataset combination or code snippet that triggers the issue), the layer of the sandbox it bypasses, and potential impact. This is a solo-maintained project, so response times aren't guaranteed, but reports will be acknowledged and addressed as soon as possible.
