# WS6 deployment report

Implemented deployment preparation. No live deployment, account creation,
commit, push, or env-file access performed.

## Files

- `Dockerfile`: Python 3.12, pinned uv image, frozen production dependencies,
  non-root runtime, one Uvicorn worker, `/data`, `/health` healthcheck.
- `.dockerignore`: excludes credentials, env files, local state and artifacts.
- `scripts/deploy.sh`: local image checks and explicit InsForge deploy mode.
- `deploy/render.yaml`: optional Render Blueprint with disk and secret inputs.
- `deploy/README.md`: host prerequisites, secrets, release checks, redeploy,
  rollback, single-process constraints and proxy behavior.
- `sv/proofpath/public_guard.py`: session caps 5/3/2, 60 requests/minute per
  connection IP, configurable shared hourly model-route cap (default 60),
  versioned 429 envelopes, expiry cleanup, reservations before await.

## Verification

- Guard import passes.
- Direct FastAPI/TestClient checks pass for create/run/agent session caps and
  health exemption. Also checks missing session, cross-session global model
  budget and per-IP request cap.
- `bash -n scripts/deploy.sh` passes.
- Initial Docker daemon check was blocked: `permission denied while trying to connect
  to the docker API at unix:///Users/abhijitbetigeri/.docker/run/docker.sock`.
  Coordinator repeated the check with escalation: Docker daemon is not
  running. No image build is claimed.
- `npx @insforge/cli current --json` did not return within the observation
  window and was stopped. Offline retry likewise did not promptly return.
  Compute access remains unknown; no projects were created or linked.

## Coordinator integration

Coordinator has wired `public_guard.install(app)` immediately after app
construction and before session middleware, plus secure cookies in public mode.
Session quotas count attempts; cookie resets remain possible, with connection-IP
and global budgets providing secondary bounds. Quotas and operator sessions
reset on process restart. One worker/replica only.

## Remaining release work

Run Docker build/run with daemon access, resolve InsForge CLI/project access,
verify host proxy IP configuration, then run WS8 smoke with `BASE_URL` on
local-mode HTTP container and public-mode HTTPS (paced to respect quotas) and
public HTTPS deployment. User enters secrets in host dashboard/private file.
Render fallback needs account/repository access and paid plan review. The public
URL requirement is not complete: deployment authorization was excluded from
this task.
