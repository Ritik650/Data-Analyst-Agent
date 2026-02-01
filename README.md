# AI Data-Analyst Agent

**Dataset + natural-language problem statement → grounded analytical report (HTML/PDF), where every number is traceable to real executed code — not LLM-hallucinated.**

Most "LLM writes an EDA summary" projects let the model invent statistics. This one doesn't: a critic agent cross-checks every numeric claim in the report against the actual stdout of sandboxed code execution before it's allowed in. Claims that can't be verified are regenerated; persistent offenders are visibly flagged in the report.

---

## Architecture

```
            POST /analyze (dataset + problem)          returns job_id immediately
                          │
             ┌────────────▼─────────────┐
             │  FastAPI (Vercel         │   GET /status/{job_id}   → progress
             │  serverless)             │   GET /report/{job_id}   → HTML/PDF/JSON
             └────────────┬─────────────┘
                          │ Celery send_task
             ┌────────────▼─────────────┐
             │  Upstash Redis            │  broker + job state + report blobs (TTL)
             └────────────┬─────────────┘
                          │
             ┌────────────▼───────────────────────────────────────────┐
             │  Celery worker (Hugging Face Docker Space / any host)  │
             │                                                        │
             │  Planner ──► plan (structured JSON, 3-5 questions)     │
             │     │                                                  │
             │  Coder ───► pandas/matplotlib code ──► SANDBOX         │
             │     ▲                │  subprocess: rlimits, timeout,  │
             │     └── error ◄──────┘  no network, import allowlist   │
             │         (retry ≤3)                                     │
             │     │                                                  │
             │  Critic ──► insight prose ──► verify every number      │
             │     ▲                          against real stdout     │
             │     └── ungrounded claims ◄────┘ (regenerate ≤2)       │
             │     │                                                  │
             │  Report ──► Jinja2 → HTML → PDF (WeasyPrint)           │
             └────────────────────────────────────────────────────────┘
```

The orchestrator is a hand-rolled explicit state machine ([agents/orchestrator.py](agents/orchestrator.py)) — plan → code (retry loop) → ground-check (regenerate loop) → summarize (ground-check again) → render.

## Free deployment stack ($0)

| Component | Service | Notes |
|---|---|---|
| API (FastAPI) | **Vercel** serverless (Hobby) | Thin front door: enqueue / status / report. 4.5MB request body limit → 4MB dataset cap |
| Async worker | **Hugging Face Docker Space** (free CPU) | Long-running Celery worker + sandbox + WeasyPrint — things serverless can't run |
| Broker / state / blobs | **Upstash Redis** (free tier) | Celery broker, job status, and report bytes with TTL — nothing touches local disk |
| LLM | **Google Gemini API** (free tier) | `gemini-2.5-flash` default, env-configurable (`GEMINI_MODEL`); free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

**Why not everything on Vercel?** Serverless functions can't host a persistent Celery worker, can't run multi-minute jobs reliably, and don't ship WeasyPrint's system libraries (Pango/Cairo). Splitting the thin async API (Vercel) from the heavy worker (HF Space) keeps the whole thing free *and* honest about the async job pattern.

**Why Redis for report storage?** Both Vercel and free container hosts have ephemeral filesystems — anything on local disk is lost on restart. Reports/charts live in Redis with a 24h TTL (charts are embedded in the HTML as base64, so a report is a single blob).

---

## Quickstart (local)

```bash
git clone <this repo> && cd Data-Analyst-Agent
cp .env.example .env          # put your GEMINI_API_KEY in .env (free: aistudio.google.com/apikey)

docker-compose up --build     # redis + api (:8000) + worker
```

Submit a job:

```bash
# 1) enqueue
curl -s -X POST http://localhost:8000/analyze \
  -F "file=@eval/test_datasets/sales.csv" \
  -F "problem=Which regions and months drive revenue? Recommend where to focus." 
# -> {"job_id": "abc123...", "poll": "/status/abc123...", ...}

# 2) poll
curl -s http://localhost:8000/status/<job_id>

# 3) fetch the report when status=done
curl -s "http://localhost:8000/report/<job_id>?format=html" -o report.html
curl -s "http://localhost:8000/report/<job_id>?format=pdf"  -o report.pdf
```

Interactive docs at `http://localhost:8000/docs`.

### Local dev without Docker

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-worker.txt            # full dependency set
# start redis (e.g. docker run -p 6379:6379 redis:7-alpine)
uvicorn api.main:app --reload                     # terminal 1
celery -A worker.tasks worker --loglevel=info --pool=solo   # terminal 2 (--pool=solo on Windows)
```

---

## Deployment (free tier)

### 1. Upstash Redis
1. Create a free database at [upstash.com](https://upstash.com) → copy the `rediss://default:...@....upstash.io:6379` URL.

### 2. Worker → Hugging Face Docker Space
1. Create a new **Docker** Space at [huggingface.co/spaces](https://huggingface.co/spaces) (free CPU basic).
2. Push this repo's contents to the Space, renaming `Dockerfile.worker` → `Dockerfile` (HF expects it at the root):
   ```bash
   cp Dockerfile.worker Dockerfile && git add Dockerfile && git push space main
   ```
3. In Space **Settings → Variables and secrets**, set `GEMINI_API_KEY` and `REDIS_URL` (the Upstash URL).
4. The Space serves a trivial health page on port 7860 while the Celery worker runs in the foreground. Note: free Spaces pause after ~48h without traffic — a free cron ping (e.g. [cron-job.org](https://cron-job.org)) keeps it warm.

### 3. API → Vercel
```bash
npm i -g vercel
vercel                        # from the repo root — vercel.json routes everything to api/index.py
vercel env add REDIS_URL      # the same Upstash URL
vercel --prod
```
The Vercel bundle installs only the slim [requirements.txt](requirements.txt); heavy pipeline deps never ship to serverless (the worker imports them lazily inside the task).

### 4. CI
GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the test suite on every push/PR. Vercel's GitHub integration can be set to deploy only on green checks.

---

## Evaluation

Reproducible at $0 — the 8 datasets are synthesized with a fixed seed (no Kaggle downloads needed):

```bash
python -m eval.generate_datasets           # writes eval/test_datasets/*.csv + problems.json
python -m eval.run_generalization_eval     # runs the full pipeline on all 8 (needs GEMINI_API_KEY)
python -m eval.grounding_audit             # independently re-verifies every claim vs execution logs
```

Results land in [results/eval_report.md](results/eval_report.md):

| Dataset | Domain | Success | Coder attempts (avg/step) | Grounding accuracy | Duration |
|---|---|---|---|---|---|
| sales.csv | Sales | — | — | — | — |
| healthcare.csv | Healthcare | — | — | — | — |
| sports.csv | Sports | — | — | — | — |
| finance.csv | Finance | — | — | — | — |
| retail.csv | Retail | — | — | — | — |
| hr.csv | HR | — | — | — | — |
| energy.csv | Energy | — | — | — | — |
| education.csv | Education | — | — | — | — |

**Headline metric:** first-pass code execution success rate **X% → Y%** with the error-feedback retry loop (populated by the eval run).

The **grounding audit** is deliberately independent: it re-extracts every number from the final report prose and re-verifies it against the recorded sandbox stdout — it audits the pipeline rather than trusting the pipeline's self-reported numbers.

---

## Security: the sandbox tradeoff (stated honestly)

Docker-per-run isolation is the correct production answer; it doesn't fit free-tier compute. The deployed version substitutes **subprocess sandboxing** ([sandbox/](sandbox/)) with these layers:

1. **`resource.setrlimit`** memory (RLIMIT_AS) and CPU caps (POSIX; the worker always runs on Linux)
2. **Hard wall-clock timeout** enforced by the parent process
3. **No network** — socket creation is monkeypatched out before user code runs
4. **Import allowlist** (pandas/numpy/scipy/matplotlib + stdlib-math only) + restricted builtins (`eval`/`exec`/`compile`/`input` removed) for the executed code
5. **`open()` confined** to the scoped per-job temp directory
6. **Stripped environment** — the subprocess never sees `GEMINI_API_KEY` or any other secret
7. The worker container runs as an **unprivileged user**

**Known limitation:** a subprocess shares the OS user with the worker, so a determined adversary using library-internal file loaders (e.g. `pd.read_csv("/etc/passwd")`) can still read files readable by that user — subprocess sandboxing hardens against resource exhaustion, network exfiltration, and the obvious escape routes, not against a motivated attacker. That's exactly the gap Docker-per-run (or gVisor/Firecracker) closes, and it's the documented tradeoff, not an oversight.

---

## Project structure

```
├── agents/
│   ├── planner.py        # problem + schema → structured JSON plan
│   ├── coder.py          # writes pandas/matplotlib code, retries on errors (≤3)
│   ├── critic.py         # grounding: verify every number vs stdout, regenerate (≤2)
│   ├── orchestrator.py   # explicit state machine tying it together
│   └── llm.py            # Gemini API wrapper (structured JSON output + rate-limit backoff)
├── sandbox/
│   ├── executor.py       # parent: subprocess spawn, timeout, chart collection
│   └── runner.py         # child harness: rlimits, no-network, import allowlist
├── report/               # Jinja2 → HTML → PDF (WeasyPrint)
├── api/                  # FastAPI + Celery producer + Redis storage (Vercel-deployable)
├── worker/               # Celery consumer task + HF Space entrypoint
├── eval/                 # dataset generator, generalization eval, grounding audit
├── tests/                # sandbox security, grounding logic, report rendering
├── vercel.json           # Vercel routing → api/index.py
├── Dockerfile.api / Dockerfile.worker / docker-compose.yml
└── .github/workflows/ci.yml
```

## Known limitations & future work

- Subprocess sandbox vs. real per-run isolation (see above) — Docker-per-run/gVisor is the upgrade path.
- 4MB dataset cap (Vercel request body limit). Larger datasets → presigned uploads to Cloudflare R2 (free 10GB) and pass a URL instead.
- Free HF Spaces sleep after ~48h idle; Vercel Hobby functions cold-start. Both are cold-start, not correctness, issues.
- Grounding verification is numeric-only; qualitative claims ("strong correlation") are not machine-checked.
- One worker = serial reports. Celery makes horizontal scaling trivial when there's budget for it.
