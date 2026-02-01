"""Celery worker task: runs the full analysis pipeline for a queued job.

Start the worker with:
    celery -A worker.tasks worker --loglevel=info --concurrency=2
(add --pool=solo on Windows dev machines)
"""
from __future__ import annotations

import tempfile
import traceback
from pathlib import Path

from api.celery_app import TASK_RUN_ANALYSIS, celery_app
from api import storage


@celery_app.task(name=TASK_RUN_ANALYSIS, bind=True)
def run_analysis(self, job_id: str, suffix: str) -> None:
    # Heavy imports stay inside the task so producer-side imports remain slim.
    from agents.orchestrator import run_pipeline
    from report.generate_report import render_html, render_pdf

    state = storage.get_status(job_id)
    if state is None:
        return  # job expired before a worker picked it up

    def notify(stage: str, progress: int) -> None:
        storage.update_status(job_id, status="running", stage=stage, progress=progress)

    dataset = storage.get_blob(job_id, f"dataset{suffix}")
    if dataset is None:
        storage.update_status(job_id, status="failed", error="Dataset blob expired.")
        return

    tmpdir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
    dataset_path = Path(tmpdir) / f"dataset{suffix}"
    dataset_path.write_bytes(dataset)

    try:
        notify("Starting pipeline", 2)
        payload = run_pipeline(
            dataset_path=dataset_path,
            problem_statement=state["problem"],
            dataset_name=state.get("filename", f"dataset{suffix}"),
            status_cb=notify,
        )

        html = render_html(payload)
        storage.save_blob(job_id, "report_html", html.encode("utf-8"))
        pdf = render_pdf(html)
        if pdf:
            storage.save_blob(job_id, "report_pdf", pdf)
        storage.save_json(job_id, "result", payload)

        storage.update_status(
            job_id, status="done", stage="Report ready", progress=100,
            metrics=payload["metrics"], pdf_available=bool(pdf),
        )
    except Exception:
        storage.update_status(
            job_id, status="failed", stage="Pipeline error",
            error=traceback.format_exc(limit=6)[-3000:],
        )
        raise
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
