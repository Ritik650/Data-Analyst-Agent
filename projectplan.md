# AI Data-Analyst Agent — Master Plan

**Goal:** An agent that takes a dataset + natural-language problem statement and produces a grounded analytical report (charts, tables, stats, recommendations) — with every number traceable to executed code, not hallucinated.

**Timeline:** 3-4 weeks
**Cost:** $0 (free-tier stack)

---

## 1. Core Concept

```
Input:  dataset (CSV/Excel/DB) + problem statement (natural language)
Output: PDF/HTML report — EDA, charts, stats tests, insights, recommendations
        grounded in real executed code output (not LLM-hallucinated numbers)
```

---

## 2. Architecture

```
Problem statement + data schema
        ↓
Planner agent (LLM) → structured analysis plan (questions, relevant columns, chart types)
        ↓
Code-execution agent → writes Pandas/matplotlib code → runs in sandbox
        ↓ (error?)
    retry loop, feed error back to agent (max N attempts)
        ↓ (success)
Critic/validation agent → checks reported numbers match code output, charts non-empty
        ↓
Report generator → Jinja2 → HTML/PDF (WeasyPrint) with exec summary, charts, tables, recs
```

**The core differentiator:** every claim in the final report is checked against real executed code output before it's allowed into the report. This is what separates it from every other "LLM writes an EDA summary" toy project.

---

## 3. Project Structure

```
data-analyst-agent/
├── agents/
│   ├── planner.py            # reads schema + problem → analysis plan
│   ├── coder.py               # writes + retries Pandas/matplotlib code
│   ├── critic.py               # grounding validation
│   └── orchestrator.py         # state machine tying the 3 agents together
├── sandbox/
│   └── executor.py             # Docker/subprocess sandboxed code runner
├── report/
│   ├── templates/report.html.j2
│   └── generate_report.py      # Jinja2 → HTML → PDF via WeasyPrint
├── api/
│   ├── main.py                 # FastAPI: POST /analyze, GET /status/{job_id}, GET /report/{job_id}
│   └── tasks.py                 # Celery tasks
├── eval/
│   ├── test_datasets/           # 8-10 varied Kaggle datasets (sales, healthcare, sports, finance)
│   ├── run_generalization_eval.py
│   └── grounding_audit.py       # % of claims verified against code output
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.worker
├── .github/workflows/ci.yml
├── results/
│   └── eval_report.md
└── README.md
```

---

## 4. Free Deployment Stack

| Component | Service | Notes |
|---|---|---|
| API (FastAPI) | Render free web service | 512MB RAM, sleeps after 15min idle, 750 free hrs/month |
| Async workers | Celery worker as a **Render Background Worker** (free tier) OR run Celery in the same container with a lightweight broker | Report generation is slow (multi-minute) — must be async, not blocking the API |
| Message broker / result backend | **Upstash Redis** free tier | Serverless, works as both Celery broker and result backend |
| Code sandbox | Local subprocess with resource limits (`resource` module: memory cap, CPU time cap, timeout) instead of a Docker-per-run | Docker-per-run needs more compute than free tiers give; subprocess sandboxing with strict resource limits is a legitimate, lighter-weight alternative — mention the tradeoff explicitly in the README |
| PDF generation | WeasyPrint (runs fine in a slim container) | Watch memory — keep report templates lightweight |
| File storage (generated reports/charts) | Store as base64/bytes in Redis with TTL, or free-tier S3-compatible storage (Cloudflare R2 free tier: 10GB) | Render free web services have an **ephemeral filesystem** — anything saved to disk is lost on restart/redeploy, so don't rely on local file storage for generated reports |

**Key constraint to design around:** Render's free web service has an ephemeral filesystem (wiped on every restart/redeploy/spin-down). Generated PDFs/charts must go to Redis (short-lived, with TTL) or a free object store like Cloudflare R2 — never assume local disk persists.

---

## 5. Week-by-Week Build Plan

### Week 1 — Sandbox + Planner + Coder Agent
- **Day 1-2:** Build the sandboxed executor first (`sandbox/executor.py`) — subprocess with `resource.setrlimit` for memory/CPU caps, a hard wall-clock timeout, and a restricted builtins/import allowlist (pandas, numpy, matplotlib, scipy only — block `os`, `subprocess`, `socket`, etc.). This is the security-critical piece; get it solid before building agents on top.
- **Day 3:** Planner agent — LLM call that takes `(problem_statement, df.dtypes, df.head())` and returns a structured JSON plan (list of sub-questions, relevant columns, suggested chart types).
- **Day 4-5:** Coder agent — LLM writes Pandas/matplotlib code per plan step, executes in sandbox, captures stdout + errors + saved chart files. On failure, feed the error message back to the LLM for a retry (cap at 3 attempts). Log attempt count per step.

### Week 2 — Critic Agent + Report Generation
- **Day 1-2:** Critic agent — for each claim the coder agent's output implies (e.g. "average revenue is $X"), verify it's traceable to the actual executed output (regex/structured extraction + comparison), not just LLM prose. Flag ungrounded claims and trigger a regeneration.
- **Day 3-4:** Report generator — Jinja2 template → HTML → PDF via WeasyPrint. Sections: executive summary, methodology, charts with captions, data tables, recommendations tied to the original problem statement.
- **Day 5:** Wire the orchestrator (`agents/orchestrator.py`) — plan → code → critic → (retry if ungrounded) → report, as an explicit state machine (hand-rolled or LangGraph, your call — hand-rolled shows you understand the mechanism).

### Week 3 — Async Architecture + Generalization Testing
- **Day 1-2:** Wrap the pipeline as a Celery task. FastAPI `POST /analyze` enqueues the job and returns a `job_id` immediately; `GET /status/{job_id}` polls state; `GET /report/{job_id}` returns the finished PDF/HTML once ready. This async pattern is the backend-engineering signal — don't skip it even though it's more work than a blocking call.
- **Day 3-5:** Generalization eval — pull 8-10 varied Kaggle datasets (sales, healthcare, sports, finance). Run each through the full pipeline. Record for each:
  - Did it complete successfully?
  - How many coder-agent retries were needed?
  - Grounding audit: what % of numeric claims in the final report trace back to real executed code output? (Write `grounding_audit.py` to parse the report and cross-check each stated number against the sandbox execution logs.)

### Week 4 — Deploy + Polish
- **Day 1:** Get `docker-compose up` working locally (API + Celery worker + Redis)
- **Day 2:** Swap Redis for Upstash, deploy API to Render as a free web service, deploy Celery worker as a Render Background Worker (or a second free web service running the worker process if Background Workers aren't free-tier eligible — verify current Render free-tier service types before committing)
- **Day 3:** Add GitHub Actions CI (`pytest` on push, gates deploy)
- **Day 4:** Re-run the generalization eval against the **deployed** endpoint. Load test with Locust for a real P95 report-generation-latency number.
- **Day 5:** Write README: architecture diagram, the eval table below, live demo + cold-start note, known limitations (subprocess sandbox vs full Docker isolation — state this as a conscious tradeoff, not an oversight), reproduction steps.

**Target eval table:**

| Dataset | Domain | Success | Coder Retries (avg) | Grounding Accuracy | Report Gen Time (P50/P95) |
|---|---|---|---|---|---|
| ... | Sales | | | | |
| ... | Healthcare | | | | |
| ... | Sports | | | | |
| ... | Finance | | | | |

Plus one aggregate line: **first-pass code execution success rate with vs without the retry loop** (e.g. "68% → 94%") — this single number is the strongest interview talking point in the whole project.

---

## 6. Key Libraries

```
pandas, numpy, scipy, matplotlib / plotly
jinja2, weasyprint       # report generation
fastapi, uvicorn
celery, redis
docker (or resource + subprocess for sandboxing on free tier)
```

---

## 7. Security Note (say this explicitly in the README/interviews)
Full Docker-per-run isolation is the "correct" production answer but doesn't fit free-tier compute. The deployed version uses subprocess sandboxing with:
- Restricted builtins/import allowlist (no `os`, `subprocess`, `socket`, `open` outside a scoped temp dir)
- `resource.setrlimit` memory and CPU caps
- Hard wall-clock timeout per execution
- No network access from within the sandbox

State this as a deliberate, documented tradeoff — "Docker-per-run sandboxing was the original design; subprocess sandboxing with resource limits was substituted for free-tier compute constraints, with the tradeoffs documented" is a strong, honest engineering statement.

---

## 8. Pitfalls to Avoid
- Don't skip the grounding audit — it's the single most differentiating metric in the project
- Don't test on only 1-2 datasets — generalization across domains is the point
- Don't make `/analyze` a blocking call — the async job pattern is deliberately part of the resume story
- Don't store generated reports on local disk in the deployed version — Render's free filesystem is ephemeral

---

## 9. Resume Bullet (once complete)

> **AI Data-Analyst Agent** | LangGraph/custom orchestration, FastAPI, Celery, Pandas, WeasyPrint, Docker
> • Built an agentic pipeline converting a dataset + natural-language problem into a grounded analytical report; LLM-generated code executes in a sandboxed environment with a self-correcting retry loop
> • Improved first-pass code execution success rate from [X]% to [Y]% via error-feedback retries; grounding audit confirmed [Z]% of reported figures trace to executed code output
> • Deployed as async FastAPI + Celery service (job-status polling) on Render + Upstash Redis; tested generalization across 8 datasets spanning finance, healthcare, retail, and sports

---

## 10. README Structure
1. One-line pitch 
2. Architecture diagram (planner → coder → critic → report loop)
3. Eval table (generalization + grounding accuracy across datasets)
4. Retry-loop success-rate before/after number
5. `docker-compose up` reproduction steps
6. Security/sandboxing tradeoff note
7. Known limitations + future work (real Docker-per-run isolation, larger dataset support)
