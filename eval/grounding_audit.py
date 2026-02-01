"""Grounding audit: independently re-verify every numeric claim in the final
report prose against the recorded sandbox execution logs.

This deliberately re-runs the verification from scratch on the saved eval log
(rather than trusting the pipeline's own numbers) — it's the audit, not the
producer. Run after run_generalization_eval.py:

    python -m eval.grounding_audit
"""
from __future__ import annotations

import json
from pathlib import Path

from agents.critic import verify

RESULTS_DIR = Path(__file__).parent.parent / "results"


def audit_record(record: dict) -> dict:
    total = grounded = 0
    flagged: list[str] = []
    all_stdout = "\n".join(s["stdout"] or "" for s in record.get("steps") or [])

    for step in record.get("steps") or []:
        if not step.get("insight"):
            continue
        g = verify(step["insight"], step["stdout"] or "", exempt_text=step["question"])
        total += g.total_claims
        grounded += g.grounded_claims
        flagged += [f"{step['question'][:40]}…: {u}" for u in g.ungrounded]

    summary_text = (record.get("executive_summary") or "") + "\n" + \
                   "\n".join(record.get("recommendations") or [])
    g = verify(summary_text, all_stdout + "\n" +
               "\n".join(s.get("insight") or "" for s in record.get("steps") or []))
    total += g.total_claims
    grounded += g.grounded_claims
    flagged += [f"summary: {u}" for u in g.ungrounded]

    return {"dataset": record["dataset"], "claims_total": total,
            "claims_grounded": grounded,
            "accuracy": round(grounded / total, 4) if total else 1.0,
            "flagged": flagged}


def main() -> None:
    log_path = RESULTS_DIR / "eval_log.json"
    records = json.loads(log_path.read_text(encoding="utf-8"))

    print(f"{'Dataset':<18} {'Claims':>7} {'Grounded':>9} {'Accuracy':>9}")
    print("-" * 48)
    totals = [0, 0]
    for record in records:
        if not record["completed"]:
            print(f"{record['dataset']:<18} {'—':>7} {'—':>9} {'FAILED':>9}")
            continue
        a = audit_record(record)
        totals[0] += a["claims_total"]
        totals[1] += a["claims_grounded"]
        print(f"{a['dataset']:<18} {a['claims_total']:>7} {a['claims_grounded']:>9} "
              f"{a['accuracy']*100:>8.1f}%")
        for f in a["flagged"]:
            print(f"    ⚠ ungrounded: {f}")
    print("-" * 48)
    overall = totals[1] / totals[0] if totals[0] else 1.0
    print(f"{'OVERALL':<18} {totals[0]:>7} {totals[1]:>9} {overall*100:>8.1f}%")


if __name__ == "__main__":
    main()
