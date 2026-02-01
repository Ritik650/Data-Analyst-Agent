"""Orchestrator: explicit state machine tying planner -> coder -> critic -> report.

    plan -> [for each question: code (retry loop) -> insight -> grounding check
    (regenerate loop)] -> summary (grounding check) -> report payload
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from agents import coder, critic, planner

StatusCallback = Callable[[str, int], None]  # (stage_description, progress 0-100)


def _load_dataframe(dataset_path: str | Path) -> pd.DataFrame:
    path = Path(dataset_path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def run_pipeline(dataset_path: str | Path, problem_statement: str,
                 dataset_name: str = "dataset",
                 status_cb: StatusCallback | None = None) -> dict:
    """Run the full analysis pipeline. Returns the report payload dict."""
    notify = status_cb or (lambda stage, progress: None)

    notify("Loading dataset", 5)
    df = _load_dataframe(dataset_path)
    schema_summary = planner.describe_dataset(df)

    notify("Planning analysis", 10)
    plan = planner.make_plan(problem_statement, schema_summary)
    questions = plan["questions"]

    steps: list[dict] = []
    for i, question in enumerate(questions, start=1):
        base = 10 + int(70 * (i - 1) / max(len(questions), 1))
        notify(f"Analyzing ({i}/{len(questions)}): {question['question'][:60]}", base)

        coded = coder.solve(question, schema_summary, str(dataset_path))
        step = {
            "question": question["question"],
            "chart_type": question.get("chart_type", "none"),
            "code": coded.code,
            "attempts": coded.attempts,
            "first_pass_success": coded.first_pass_success,
            "success": coded.success,
            "stdout": coded.execution.stdout if coded.execution else "",
            "error": None if coded.success else (coded.execution.error if coded.execution else "no execution"),
            "charts": coded.execution.charts if (coded.execution and coded.success) else [],
            "insight": None,
            "grounding": None,
        }
        if coded.success:
            insight, grounding = critic.grounded_insight(question["question"], step["stdout"])
            step["insight"] = insight
            step["grounding"] = grounding.to_dict()
        steps.append(step)

    notify("Writing executive summary", 85)
    successful = [s for s in steps if s["success"] and s["insight"]]
    all_stdout = "\n\n".join(s["stdout"] for s in successful)
    if successful:
        summary, summary_grounding = critic.grounded_summary(
            problem_statement, [s["insight"] for s in successful], all_stdout
        )
    else:
        summary = {"executive_summary": "No analysis step completed successfully; "
                                        "see per-question errors below.",
                   "recommendations": []}
        summary_grounding = critic.GroundingResult()

    notify("Assembling report", 95)
    metrics = _compute_metrics(steps, summary_grounding)

    return {
        "title": plan.get("title") or "Data Analysis Report",
        "problem_statement": problem_statement,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "dataset": {
            "filename": dataset_name,
            "rows": int(len(df)),
            "cols": int(len(df.columns)),
            "columns": [{"name": c, "dtype": str(t)} for c, t in df.dtypes.items()],
        },
        "executive_summary": summary["executive_summary"],
        "recommendations": summary["recommendations"],
        "summary_grounding": summary_grounding.to_dict(),
        "steps": steps,
        "metrics": metrics,
    }


def _compute_metrics(steps: list[dict], summary_grounding: critic.GroundingResult) -> dict:
    total = len(steps)
    successes = sum(1 for s in steps if s["success"])
    first_pass = sum(1 for s in steps if s["first_pass_success"])
    claims_total = summary_grounding.total_claims
    claims_grounded = summary_grounding.grounded_claims
    for s in steps:
        if s["grounding"]:
            claims_total += s["grounding"]["total_claims"]
            claims_grounded += s["grounding"]["grounded_claims"]
    return {
        "questions_total": total,
        "questions_succeeded": successes,
        "first_pass_success_rate": round(first_pass / total, 4) if total else 0.0,
        "final_success_rate": round(successes / total, 4) if total else 0.0,
        "total_coder_attempts": sum(s["attempts"] for s in steps),
        "claims_total": claims_total,
        "claims_grounded": claims_grounded,
        "grounding_accuracy": round(claims_grounded / claims_total, 4) if claims_total else 1.0,
    }
