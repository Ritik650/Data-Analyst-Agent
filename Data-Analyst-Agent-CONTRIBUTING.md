# Contributing to AI Data-Analyst Agent

Thanks for your interest. Issues and PRs are welcome, especially around sandbox hardening, grounding accuracy, and support for additional data formats.

## Development setup

```bash
git clone https://github.com/Ritik650/Data-Analyst-Agent.git
cd Data-Analyst-Agent
cp .env.example .env               # add GEMINI_API_KEY

docker-compose up --build          # redis + api (:8000) + worker
```

Or without Docker:

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-worker.txt
# start redis separately, then:
uvicorn api.main:app --reload                     # terminal 1
celery -A worker.tasks worker --loglevel=info --pool=solo   # terminal 2
```

## Before opening a PR

Run the test suite — it covers sandbox security, grounding logic, and report rendering:

```bash
pytest tests/
```

If your change touches the pipeline's numeric behavior (planner questions, coder retries, critic thresholds), run the evaluation harness against the synthetic datasets before and after your change, and include the before/after numbers in your PR description:

```bash
python -m eval.generate_datasets
python -m eval.run_generalization_eval
python -m eval.grounding_audit
```

## Working on the sandbox

The sandbox ([sandbox/](sandbox)) is the most security-sensitive part of this codebase. If you're changing it:

- Read the [Security section](README.md#security-the-sandbox-tradeoff-stated-honestly) in the README first — it documents the current threat model and its known gap (shared-OS-user file access).
- Any change that widens the import allowlist, the builtin allowlist, or the `open()` scope needs an explicit justification in the PR — these are the primary attack surface.
- Add a test in `tests/` demonstrating the specific thing your change blocks or permits.

## Extending agent behavior

- **Planner** ([agents/planner.py](agents/planner.py)) — changes to plan structure should keep output as parseable structured JSON; downstream agents depend on the schema.
- **Coder** ([agents/coder.py](agents/coder.py)) — the retry loop (≤3 attempts) expects errors to come back as plain stdout/stderr text from the sandbox; keep that contract if you change sandbox output format.
- **Critic** ([agents/critic.py](agents/critic.py)) — grounding logic should stay numeric-claim-focused per the documented limitation (qualitative claims aren't machine-checked); if you extend it to qualitative claims, update that limitation in the README rather than silently expanding scope.

## Style

- Keep the explicit state machine in `agents/orchestrator.py` readable as a state machine — avoid folding control flow into individual agent methods.
- New report sections go through the existing Jinja2 → HTML → PDF path in `report/`, not a separate rendering path.

## Security issues

Please don't open a public issue for sandbox escape or other security concerns — see [SECURITY.md](SECURITY.md) instead.
