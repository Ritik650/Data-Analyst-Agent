"""Redis-backed job state + blob storage.

Everything lives in Redis with a TTL because both Vercel functions and free
container hosts have ephemeral filesystems — nothing may rely on local disk.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import redis

import config

_r: redis.Redis | None = None


def r() -> redis.Redis:
    global _r
    if _r is None:
        _r = redis.Redis.from_url(config.REDIS_URL)
    return _r


def _key(job_id: str, suffix: str) -> str:
    return f"job:{job_id}:{suffix}"


# --- job status ---

def init_job(job_id: str, problem: str, filename: str) -> None:
    status = {
        "job_id": job_id,
        "status": "queued",
        "stage": "Waiting for a worker",
        "progress": 0,
        "error": None,
        "problem": problem,
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": None,
    }
    r().set(_key(job_id, "status"), json.dumps(status), ex=config.REPORT_TTL_SECONDS)


def update_status(job_id: str, **fields) -> None:
    raw = r().get(_key(job_id, "status"))
    status = json.loads(raw) if raw else {"job_id": job_id}
    status.update(fields)
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    r().set(_key(job_id, "status"), json.dumps(status), ex=config.REPORT_TTL_SECONDS)


def get_status(job_id: str) -> dict | None:
    raw = r().get(_key(job_id, "status"))
    return json.loads(raw) if raw else None


# --- blobs (dataset upload, rendered reports, result payloads) ---

def save_blob(job_id: str, name: str, data: bytes) -> None:
    r().set(_key(job_id, name), data, ex=config.REPORT_TTL_SECONDS)


def get_blob(job_id: str, name: str) -> bytes | None:
    return r().get(_key(job_id, name))


def save_json(job_id: str, name: str, obj: dict) -> None:
    save_blob(job_id, name, json.dumps(obj).encode("utf-8"))


def get_json(job_id: str, name: str) -> dict | None:
    raw = get_blob(job_id, name)
    return json.loads(raw) if raw else None
