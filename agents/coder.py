"""Coder agent: writes pandas/matplotlib code per plan step and retries on errors."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import config
from agents import llm
from sandbox.executor import ExecutionResult, run_code

CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

SYSTEM = """You write Python analysis code that runs inside a locked-down sandbox.

Hard rules — code violating any of them will crash:
- A pandas DataFrame named `df` is ALREADY LOADED with the dataset. `pd`, `np`, `plt` are pre-imported.
- Only these imports are allowed: pandas, numpy, scipy, matplotlib, math, statistics,
  json, datetime, itertools, functools, collections, re, io, random, string, warnings.
- NO file reads, NO network, NO os/sys/subprocess.
- Never call plt.show(). Save each chart with plt.savefig("chart_<n>.png", dpi=120, bbox_inches="tight")
  then plt.close(). Give charts titles and axis labels.
- Write a plain top-to-bottom script (no functions, no __main__ guard).

Output requirements:
- print() every key numeric finding with a clear label, e.g.
    print(f"average_monthly_revenue = {value:.2f}")
- printed numbers are the ONLY source of truth for the final report, so print
  everything the finding depends on (group values, correlation coefficients,
  p-values, percentages, counts).
- Round printed floats to at most 4 decimals. Keep total output under ~80 lines.

Respond with ONE ```python code block and nothing else."""


@dataclass
class CoderResult:
    success: bool
    code: str = ""
    execution: ExecutionResult | None = None
    attempts: int = 0
    first_pass_success: bool = False
    attempt_errors: list[str] = field(default_factory=list)


def extract_code(text: str) -> str:
    match = CODE_FENCE_RE.search(text)
    return (match.group(1) if match else text).strip()


def solve(question: dict, schema_summary: str, dataset_path: str,
          max_attempts: int = config.MAX_CODER_RETRIES) -> CoderResult:
    """Generate + execute code for one plan step, feeding errors back on failure."""
    result = CoderResult(success=False)
    user = (
        f"DATASET SCHEMA:\n{schema_summary}\n\n"
        f"QUESTION: {question['question']}\n"
        f"RELEVANT COLUMNS: {', '.join(question.get('columns', []))}\n"
        f"SUGGESTED APPROACH: {question.get('analysis_approach', '')}\n"
        f"CHART: {question.get('chart_type', 'none')}\n\n"
        "Write the analysis code."
    )
    messages_context = user

    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt
        raw = llm.complete(SYSTEM, messages_context)
        code = extract_code(raw)
        execution = run_code(code, dataset_path)
        result.code, result.execution = code, execution

        if execution.success:
            result.success = True
            result.first_pass_success = attempt == 1
            return result

        result.attempt_errors.append(execution.error or "unknown error")
        messages_context = (
            f"{user}\n\nYour previous attempt failed.\n"
            f"PREVIOUS CODE:\n```python\n{code}\n```\n\n"
            f"ERROR:\n{execution.error}\n\n"
            "Fix the error and return the full corrected script."
        )
    return result
