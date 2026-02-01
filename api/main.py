"""FastAPI app — the thin async front door.

POST /analyze          enqueue a job, return job_id immediately
GET  /status/{job_id}  poll job state
GET  /report/{job_id}  fetch the finished report (html | pdf | json)

Deployable to Vercel serverless (see api/index.py) or run with uvicorn locally.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

import config
from api import storage
from api.celery_app import TASK_RUN_ANALYSIS, celery_app

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

app = FastAPI(
    title="AI Data-Analyst Agent",
    description="Dataset + natural-language problem statement -> grounded analytical report. "
                "Every number in the report is traceable to real executed code output.",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "service": "AI Data-Analyst Agent",
        "endpoints": {
            "POST /analyze": "multipart form: file=<csv/xlsx>, problem=<text> -> {job_id}",
            "GET /status/{job_id}": "job state + progress",
            "GET /report/{job_id}?format=html|pdf|json": "finished report",
            "GET /docs": "interactive OpenAPI docs",
        },
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/analyze", status_code=202)
async def analyze(file: UploadFile = File(...), problem: str = Form(...)):
    suffix = Path(file.filename or "upload.csv").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Use CSV or Excel.")
    if not problem.strip():
        raise HTTPException(400, "A problem statement is required.")

    data = await file.read()
    if len(data) > config.MAX_DATASET_BYTES:
        raise HTTPException(413, f"Dataset exceeds {config.MAX_DATASET_BYTES // (1024*1024)}MB limit.")
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")

    job_id = uuid.uuid4().hex
    storage.save_blob(job_id, f"dataset{suffix}", data)
    storage.init_job(job_id, problem=problem.strip(), filename=file.filename or f"upload{suffix}")
    celery_app.send_task(TASK_RUN_ANALYSIS, args=[job_id, suffix])

    return {"job_id": job_id, "status": "queued",
            "poll": f"/status/{job_id}", "report": f"/report/{job_id}"}


@app.get("/status/{job_id}")
def status(job_id: str):
    state = storage.get_status(job_id)
    if state is None:
        raise HTTPException(404, "Unknown job_id (jobs expire after the report TTL).")
    return state


@app.get("/report/{job_id}")
def report(job_id: str, format: str = "html"):
    state = storage.get_status(job_id)
    if state is None:
        raise HTTPException(404, "Unknown job_id (jobs expire after the report TTL).")
    if state["status"] == "failed":
        raise HTTPException(422, f"Job failed: {state.get('error')}")
    if state["status"] != "done":
        return JSONResponse(status_code=409, content={
            "detail": "Report not ready yet.", "status": state["status"],
            "stage": state.get("stage"), "progress": state.get("progress"),
        })

    if format == "json":
        payload = storage.get_json(job_id, "result")
        if payload is None:
            raise HTTPException(404, "Result payload expired.")
        return payload
    if format == "pdf":
        pdf = storage.get_blob(job_id, "report_pdf")
        if pdf is None:
            raise HTTPException(404, "PDF was not generated for this job (HTML is available).")
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="report_{job_id}.pdf"'})
    html = storage.get_blob(job_id, "report_html")
    if html is None:
        raise HTTPException(404, "Report expired.")
    return Response(html, media_type="text/html")
