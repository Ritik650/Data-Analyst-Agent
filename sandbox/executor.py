"""Parent-side sandboxed code runner.

Spawns ``python -I runner.py`` in a scoped temp directory with a stripped
environment, enforces the wall-clock timeout, and collects stdout / errors /
saved chart PNGs.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import config

RUNNER_PATH = Path(__file__).parent / "runner.py"
RESULT_MARKER = "__SANDBOX_RESULT__"
MAX_CHARTS = 8
MAX_CHART_BYTES = 2 * 1024 * 1024

# Env vars the interpreter genuinely needs on each platform. Everything else
# (API keys, tokens, cloud creds) is deliberately NOT inherited.
_ENV_PASSTHROUGH = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL")


@dataclass
class ExecutionResult:
    success: bool
    stdout: str = ""
    error: str | None = None
    charts: list[dict] = field(default_factory=list)  # [{"filename", "data_b64"}]
    duration_seconds: float = 0.0


def _minimal_env(workdir: Path) -> dict:
    env = {k: os.environ[k] for k in _ENV_PASSTHROUGH if k in os.environ}
    env["MPLCONFIGDIR"] = str(workdir / ".mpl")
    env["HOME"] = str(workdir)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _collect_charts(workdir: Path) -> list[dict]:
    charts = []
    for png in sorted(workdir.glob("*.png"))[:MAX_CHARTS]:
        data = png.read_bytes()
        if 0 < len(data) <= MAX_CHART_BYTES:
            charts.append({
                "filename": png.name,
                "data_b64": base64.b64encode(data).decode("ascii"),
            })
    return charts


def run_code(
    code: str,
    dataset_path: str | Path,
    timeout: int = config.SANDBOX_TIMEOUT_SECONDS,
    mem_mb: int = config.SANDBOX_MEMORY_MB,
    cpu_seconds: int = config.SANDBOX_CPU_SECONDS,
) -> ExecutionResult:
    dataset_path = Path(dataset_path)
    workdir = Path(tempfile.mkdtemp(prefix="sandbox_"))
    started = time.monotonic()
    try:
        (workdir / "code.py").write_text(code, encoding="utf-8")
        shutil.copyfile(dataset_path, workdir / f"dataset{dataset_path.suffix.lower()}")
        (workdir / ".mpl").mkdir(exist_ok=True)

        cmd = [sys.executable, "-I", str(RUNNER_PATH), str(workdir), str(mem_mb), str(cpu_seconds)]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(workdir),
                env=_minimal_env(workdir),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout}s (wall-clock limit).",
                duration_seconds=time.monotonic() - started,
            )

        duration = time.monotonic() - started
        result_line = next(
            (ln for ln in (proc.stdout or "").splitlines() if ln.startswith(RESULT_MARKER)),
            None,
        )
        if result_line is None:
            stderr_tail = (proc.stderr or "")[-2000:]
            return ExecutionResult(
                success=False,
                error=f"Sandbox crashed (exit {proc.returncode}). stderr:\n{stderr_tail}",
                duration_seconds=duration,
            )

        payload = json.loads(result_line[len(RESULT_MARKER):])
        return ExecutionResult(
            success=bool(payload["ok"]),
            stdout=payload.get("stdout", ""),
            error=payload.get("error"),
            charts=_collect_charts(workdir) if payload["ok"] else [],
            duration_seconds=duration,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
