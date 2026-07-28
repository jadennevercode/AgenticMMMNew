# Agentic MMM — Backend

Real backend for the AI-Native Marketing Mix Modeling platform. Replaces the
frontend mock engine with:

- **Real data** — ingests the actual Danone China MMM reference files
  (`../reference/`): the 23.8k-row modeling dataset, factor tree, KBQs,
  validation rules, data dictionary, and 12 interview transcripts.
- **Real statistics** — a dependency-light OLS MMM engine (`app/mmm/`):
  adstock + Hill saturation + multivariate regression (numpy `lstsq`),
  contribution decomposition, ROI, response curves, and technical validation
  (R² / MAPE / Durbin-Watson / VIF) with honest red flags.
- **Real LLM reasoning** — Volcano Ark `ark-code-latest` (OpenAI-compatible)
  drives the cognitive/narrative agent steps grounded in the real artifacts.

No mock data. The full 31-task, 5-stage, 5-agent workflow runs end-to-end on the
real Danone Mizone case.

## Architecture

```
app/
├── main.py            FastAPI REST API consumed by the React frontend
├── config.py          settings (.env)
├── llm/volcano.py     Volcano Ark client + robust JSON parsing/repair
├── ingest/            real reference-data parsers (xlsx/xlsm/docx)
├── mmm/               OLS MMM engine (transforms, ols, pivot, engine)
├── domain/            Pydantic models (mirror frontend types.ts) + 31-task blueprint
├── services/          (artifact/task/gate/knowledge/context-bus concerns live in store+engine)
├── agents/            per-task handlers (business/data/model/report/uploads)
├── orchestrator/      DAG engine + autopilot runner
└── store/             JSON-persisted project state
```

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# .env holds VOLCANO_API_KEY etc. (gitignored). Rotate the key periodically.
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then drive the pipeline:

```bash
curl -XPOST localhost:8000/api/reset
curl -XPOST localhost:8000/api/run -H 'content-type: application/json' -d '{"autopilot":true}'
# poll progress
curl localhost:8000/api/run/status
curl localhost:8000/api/state
```

The frontend (`../frontend`, `npm run dev`) reads `VITE_API_BASE` and renders
the live state. A full autopilot run on the real data takes ~8 minutes
(reasoning-model latency dominates).

## Tests

```bash
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py     # control-flow smoke tests
.venv/bin/python -m app.mmm._test_synthetic               # OLS correctness on known data
.venv/bin/python -m app.mmm._test_real                    # MMM on the real dataset
.venv/bin/python -m app.ingest._smoke                     # all real-data loaders
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | liveness + running flag |
| GET  | `/api/meta` | stages / agents / artifacts / tasks blueprint |
| GET  | `/api/state` | full project state (camelCase, matches frontend types) |
| POST | `/api/reset` | reset to a fresh project |
| POST | `/api/run` | start autopilot (background); `{autopilot, max_steps}` |
| GET  | `/api/run/status` | run progress |
| POST | `/api/decisions/{id}/resolve` | `{optionId, note}` |
| POST | `/api/assignments/{id}/submit` | `{note}` |
| POST | `/api/proposals/{id}/resolve` | `{accept}` |
| POST | `/api/insights/{id}/resolve` | `{actioned}` |
| POST | `/api/ai-choices/{id}` | `{optionId}` |
| POST | `/api/assistant` | `{text}` → grounded answer |
```
