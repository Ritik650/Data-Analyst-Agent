"""Generalization eval: run the full pipeline over all test datasets.

Records per-dataset: success, coder retries, grounding accuracy, wall time.
Writes results/eval_log.json (raw, used by grounding_audit.py) and
results/eval_report.md (the README table).

Run:  python -m eval.generate_datasets && python -m eval.run_generalization_eval
Requires GEMINI_API_KEY. Optionally: --only sales.csv
(Free-tier Gemini rate limits may slow the run — the LLM wrapper backs off on 429s.)
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from agents.orchestrator import run_pipeline

DATASETS_DIR = Path(__file__).parent / "test_datasets"
RESULTS_DIR = Path(__file__).parent.parent / "results"


def run_one(filename: str, meta: dict) -> dict:
    path = DATASETS_DIR / filename
    started = time.monotonic()
    record = {"dataset": filename, "domain": meta["domain"], "completed": False,
              "error": None, "duration_seconds": None, "metrics": None, "steps": None}
    try:
        payload = run_pipeline(path, meta["problem"], dataset_name=filename,
                               status_cb=lambda s, p: print(f"    [{p:3d}%] {s}"))
        record["completed"] = True
        record["metrics"] = payload["metrics"]
        # keep what the grounding audit needs: prose + raw stdout per step
        record["steps"] = [
            {"question": s["question"], "insight": s["insight"], "stdout": s["stdout"],
             "attempts": s["attempts"], "success": s["success"],
             "grounding": s["grounding"]}
            for s in payload["steps"]
        ]
        record["executive_summary"] = payload["executive_summary"]
        record["recommendations"] = payload["recommendations"]
    except Exception:
        record["error"] = traceback.format_exc(limit=4)
    record["duration_seconds"] = round(time.monotonic() - started, 1)
    return record


def write_markdown(records: list[dict]) -> str:
    lines = [
        "# Generalization Eval Report", "",
        "| Dataset | Domain | Success | Coder attempts (avg/step) | Grounding accuracy | Duration |",
        "|---|---|---|---|---|---|",
    ]
    fp_rates, final_rates = [], []
    for r in records:
        if r["completed"]:
            m = r["metrics"]
            avg_attempts = m["total_coder_attempts"] / max(m["questions_total"], 1)
            fp_rates.append(m["first_pass_success_rate"])
            final_rates.append(m["final_success_rate"])
            lines.append(
                f"| {r['dataset']} | {r['domain']} | "
                f"{m['questions_succeeded']}/{m['questions_total']} | {avg_attempts:.2f} | "
                f"{m['grounding_accuracy']*100:.1f}% | {r['duration_seconds']}s |")
        else:
            lines.append(f"| {r['dataset']} | {r['domain']} | FAILED | — | — | {r['duration_seconds']}s |")
    if fp_rates:
        fp = 100 * sum(fp_rates) / len(fp_rates)
        fin = 100 * sum(final_rates) / len(final_rates)
        lines += ["", f"**First-pass code execution success rate: {fp:.1f}% -> "
                      f"{fin:.1f}% with the error-feedback retry loop.**"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single dataset, e.g. sales.csv")
    args = parser.parse_args()

    problems = json.loads((DATASETS_DIR / "problems.json").read_text(encoding="utf-8"))
    if args.only:
        problems = {args.only: problems[args.only]}

    records = []
    for filename, meta in problems.items():
        print(f"\n=== {filename} ({meta['domain']}) ===")
        records.append(run_one(filename, meta))

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "eval_log.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    md = write_markdown(records)
    (RESULTS_DIR / "eval_report.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    main()
