# Deployment plan

Three layers, in order of reliability for the live demo:

| Layer | What | Used for |
|---|---|---|
| **1. Local (primary)** | App on the laptop at `127.0.0.1:8001`, Pulse on `:8000` | The live four-minute demo |
| **2. Public demo URL (secondary)** | One container on a cloud host | Judges clicking a link after the demo; submission form |
| **3. Recorded fallbacks** | "Recorded replay" mode + the submission video | Network or API failure on stage |

## 1. Local

- `uv sync && uv run uvicorn sv.proofpath.app:app --host 127.0.0.1 --port 8001`
- `scripts/demo_reset.sh` clears only ProofPath demo state (`PROOFPATH_DATA_DIR`) and re-seeds
  fixtures; never touches `runs/` or Pulse.
- **Pre-demo checklist** (5 minutes before going on):
  - reset
  - `GET /health` reports models reachable (Respan, Vercel/Jev)
  - one warm-up POC run, then reset again
  - browser zoom 125%, both tabs open (homepage, operator view)
  - replay file ready

## 2. Public demo URL

**Why not Vercel serverless:** the POC worker is a long-lived in-process loop and SQLite needs a
persistent filesystem. Serverless functions have neither. Use a single always-on container.

**Recommended host: Fly.io or Render** (one Docker container, one small persistent volume for
`PROOFPATH_DATA_DIR`). Railway is equivalent. Pick whichever account already exists. The
user's account status is still to confirm.

**Container:**
- `python:3.12-slim` + uv, `uv sync --frozen`
- `uvicorn sv.proofpath.app:app --host 0.0.0.0 --port 8080`
- healthcheck on `/health`
- volume mounted at `/data`, with `PROOFPATH_DATA_DIR=/data`

**Secrets** (platform secret store only, never in the image or repo):

| Variable | Purpose |
|---|---|
| `RESPAN_API_KEY`, `RESPAN_BASE_URL` | open models + fallbacks via Respan (`sv/llm.py` reads env first) |
| `AI_GATEWAY_API_KEY` | Jev via Vercel AI Gateway |
| `PROOFPATH_OPERATOR_TOKEN` | operator actions (approve/reject update, reset) |
| `PROOFPATH_DEMO_MODE=public` | enables the public-demo guards below |
| `PROOFPATH_COFRAME_PROJECT_ID` | only if a real project exists |

**Public-demo guards.** The README says public deployment needs real identity first; this is a
labeled demo of fictional data, so the minimum is:
- fictional fixtures only; free-text briefs are not stored beyond the session and are never sent
  to Coframe
- per-session caps: 5 evaluations, 3 POC runs, 2 agent evaluations, global model-call budget per
  hour (protects the $15 Vercel credit and Respan credits)
- rate limit per IP; HTTPS from the host; operator token required for update/approve/reset
- optional: password-protected share link if the event asks for a private submission
- nightly (or on-demand) reset via the operator route

**Deploy steps:**
1. `scripts/build_check.sh` runs tests + smoke against the container locally.
2. Create the app and volume on the chosen host.
3. Set secrets.
4. Deploy.
5. Run smoke against the public URL.
6. Put the URL in the submission and on the final slide.

Rollback = redeploy the previous image tag.

## 3. Fallbacks

- **Replay:** export one full evaluation after the final rehearsal. If live calls fail mid-demo,
  switch to replay (badge visible) and say so. Never fake a live POC.
- **Model outage:** brief parsing falls back to the preset chip; the agent falls back to
  "Rule-based evaluation". The demo survives with zero model calls.
- **Video:** the submission video doubles as the last-resort demo.

## Cost estimate for the day

- Open models via OpenRouter on Respan credits: cents per full demo run.
- Jev: about $0.000015 per call.
- Simulator sweep (3 presets × 4 models × 2 arms × n=3 = 72 runs): well under $1.
- Host: free/hobby tier is enough for one small container.
