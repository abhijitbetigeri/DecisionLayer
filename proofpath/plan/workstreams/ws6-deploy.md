# WS6: Public deployment (external agent)

**Time box: 60 minutes.** Goal: a public HTTPS URL for the Evaluation Workspace that judges can
click, without slowing the build. The laptop stays the primary demo.

**Read first:** `../README.md` (rules), `../deployment.md` (layers, secrets, public-demo guards),
`sv/proofpath/app.py` (do not edit).

## Files you own

- `Dockerfile`, `.dockerignore`
- `deploy/` (any host config, e.g. `deploy/README.md`, `deploy/render.yaml`, `deploy/railway.json`)
- `scripts/deploy.sh`
- `sv/proofpath/public_guard.py` (middleware the coordinator wires in)
- Your status file: `proofpath/plan/status/ws6.md`

## Host choice, in order (stop at the first that works)

1. **InsForge compute** (the user is already logged in to InsForge; runs on Fly.io under the hood).
   - It's a **private preview, gated per project**, so first check access with the
     `insforge-cli` skill (`references/compute-deploy.md`).
   - Use image mode or source mode. Source mode needs `flyctl` on PATH (install script; no Fly
     account needed; never run `flyctl deploy` with personal credentials).
   - If access is denied, record the exact error in your status file and move on.
2. **Railway** or **Render** (needs the user to create an account, GitHub login, about 2 minutes). Ask the
   user through your status file; don't create accounts yourself.
3. **Not Vercel serverless:** the POC worker is a long-lived thread, and SQLite needs a persistent
   process. Do not spend time trying.

## Container

- `python:3.12-slim` + `uv`, then `uv sync --frozen --no-dev`
- `CMD uvicorn sv.proofpath.app:app --host 0.0.0.0 --port 8080`
- `PROOFPATH_DATA_DIR=/data` (ephemeral is acceptable: fixtures re-seed on start)
- Healthcheck: `/health`
- Exclude from the image: `.env`, `.venv`, `.proofpath-data`, `runs/*.jsonl`, `.git`

## Secrets (host secret store only; never in image, repo or logs)

- `RESPAN_API_KEY`, `RESPAN_BASE_URL=https://api.respan.ai`: `sv/llm.py` reads env first
- `AI_GATEWAY_API_KEY`: Jev
- `PROOFPATH_OPERATOR_TOKEN`: generate a fresh random one and give it to the user privately
- `PROOFPATH_DEMO_MODE=public`

Ask the user to paste secret values into the host's dashboard or CLI themselves. **Never read
`.env`.**

## `public_guard.py`

A Starlette middleware, active only when `PROOFPATH_DEMO_MODE=public`:
- per-session caps: 5 evaluations, 3 POC runs, 2 agent evaluations
- per-IP rate limit: about 60 requests/min
- a global hourly cap on model-backed routes (`POST /evaluations`, `/agent-evaluation`)
- clear 429 envelopes in the `{schema_version, error}` shape

Export `install(app)`; the coordinator adds one line to `app.py`.

## Done when

- The container builds and runs locally (or on the remote builder).
- The public URL serves `/`, `/health` and a full API journey (create → confirm → run → report)
  in the smoke script.
- Guards return 429 past the caps.
- `deploy/README.md` has exact redeploy and rollback steps.
