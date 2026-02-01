"""Harness executed INSIDE the sandbox subprocess — never imported by the app.

Usage:  python -I runner.py <workdir> <mem_mb> <cpu_seconds>

Expects <workdir>/code.py and <workdir>/dataset.<csv|xlsx>. Charts are saved by
the analysed code into <workdir>. A single JSON result line (prefixed with
RESULT_MARKER) is printed to the real stdout at the end.

Defense layers (see README for the honest threat-model discussion):
  1. resource.setrlimit memory + CPU caps (POSIX; no-op on Windows dev machines)
  2. wall-clock timeout enforced by the parent process
  3. network access disabled (socket monkeypatch)
  4. import allowlist + restricted builtins for the executed user code
  5. open() confined to the scoped working directory
  6. environment stripped by the parent (no API keys/secrets in this process)
"""
import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

RESULT_MARKER = "__SANDBOX_RESULT__"

ALLOWED_MODULES = {
    "pandas", "numpy", "scipy", "matplotlib", "math", "statistics", "json",
    "datetime", "itertools", "functools", "collections", "re", "io", "random",
    "string", "textwrap", "warnings", "typing", "decimal", "fractions", "time",
    "operator", "bisect", "heapq", "calendar",
}

STDOUT_CAP = 20_000  # chars of captured stdout returned to the agent


def apply_resource_limits(mem_mb: int, cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:
        return  # Windows dev machine — wall-clock timeout still applies
    limit = mem_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def disable_network() -> None:
    import socket

    def _blocked(*_a, **_k):
        raise RuntimeError("network access is disabled in the sandbox")

    socket.socket = _blocked          # type: ignore[misc]
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked


def build_restricted_builtins(workdir: Path):
    import builtins as real_builtins

    real_import = real_builtins.__import__
    real_open = real_builtins.open

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if level == 0 and root not in ALLOWED_MODULES:
            raise ImportError(
                f"import of '{name}' is blocked in the sandbox "
                f"(allowed: {', '.join(sorted(ALLOWED_MODULES))})"
            )
        return real_import(name, globals, locals, fromlist, level)

    def guarded_open(file, mode="r", *args, **kwargs):
        try:
            path = Path(file).resolve()
        except TypeError:
            raise PermissionError("only filesystem paths may be opened in the sandbox")
        if not (path == workdir or path.is_relative_to(workdir)):
            raise PermissionError(f"opening files outside the sandbox workdir is blocked: {file}")
        return real_open(path, mode, *args, **kwargs)

    safe = {name: getattr(real_builtins, name) for name in dir(real_builtins)}
    for banned in ("eval", "exec", "compile", "input", "breakpoint", "exit",
                   "quit", "help", "license", "credits", "copyright"):
        safe.pop(banned, None)
    safe["__import__"] = guarded_import
    safe["open"] = guarded_open
    return safe


def main() -> None:
    workdir = Path(sys.argv[1]).resolve()
    mem_mb, cpu_seconds = int(sys.argv[2]), int(sys.argv[3])

    disable_network()

    import os
    os.chdir(workdir)  # savefig with relative paths lands in the workdir
    os.environ.setdefault("MPLCONFIGDIR", str(workdir / ".mpl"))

    # Heavy imports happen before tight limits so RLIMIT_AS only has to cover
    # them plus user-code growth (default cap accounts for this).
    apply_resource_limits(mem_mb, cpu_seconds)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    dataset = next(p for p in workdir.iterdir() if p.stem == "dataset")
    if dataset.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(dataset)
    else:
        df = pd.read_csv(dataset)

    code = (workdir / "code.py").read_text(encoding="utf-8")
    captured = io.StringIO()
    result = {"ok": True, "stdout": "", "error": None}

    exec_globals = {
        "__builtins__": build_restricted_builtins(workdir),
        "__name__": "__main__",
        "df": df,
        "pd": pd,
        "np": np,
        "plt": plt,
    }
    try:
        with redirect_stdout(captured):
            exec(compile(code, "analysis.py", "exec"), exec_globals)
        plt.close("all")
    except BaseException:
        result["ok"] = False
        result["error"] = traceback.format_exc(limit=8)

    result["stdout"] = captured.getvalue()[-STDOUT_CAP:]
    sys.__stdout__.write(RESULT_MARKER + json.dumps(result) + "\n")
    sys.__stdout__.flush()


if __name__ == "__main__":
    main()
