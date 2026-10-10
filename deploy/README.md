# Decision Layer public demo deployment

One process and one replica only: the worker, session quotas, operator sessions,
and SQLite state are local. This is a fictional-data demo. Use the laptop for
stage presentations. Deployment is prepared but has not been executed.

## Verify locally

Run `scripts/deploy.sh check`, then:

```bash
docker run --rm -p 8080:8080 -e PROOFPATH_DEMO_MODE=local decision-layer:local
curl --fail http://127.0.0.1:8080/health
BASE_URL=http://127.0.0.1:8080 scripts/smoke.sh
```

Use local mode for HTTP localhost: public-mode cookies require HTTPS.
The smoke script is owned by WS8. The image
contains only `sv`, project metadata, and installed dependencies. Env files,
CLI connection credentials, run artifacts and local databases are excluded.
Runtime is a non-root user. Mounted `/data` must be writable by UID 10001.

## InsForge, preferred when compute access is available

Read-only prerequisites: `npx @insforge/cli current --json`, then
`npx @insforge/cli compute list --json` for the current linked project. Do not
create or link an unrelated project merely to test compute. Source deployment
requires `flyctl` on PATH, but all deployment commands go through InsForge.

The user supplies a private env file outside the repo with:
`PROOFPATH_DEMO_MODE=public`, `PROOFPATH_DATA_DIR=/data`,
`PROOFPATH_OPERATOR_TOKEN` (a newly generated random token), `RESPAN_API_KEY`,
`RESPAN_BASE_URL=https://api.respan.ai`, and `AI_GATEWAY_API_KEY`.
Optional `PROOFPATH_MODEL_HOURLY_CAP=60` bounds model-route attempts.

After deployment authorization:

```bash
DEPLOY_ENV_FILE=/absolute/private/path scripts/deploy.sh insforge
```

The script does not print or source the secret file. InsForge handles its upload.
Save the returned service ID, endpoint, and image URL in private release notes.
Re-running deploy with the same name redeploys source. Roll back with
`npx @insforge/cli compute update SERVICE_ID --image PREVIOUS_IMAGE_URL`.
No persistent-volume capability is assumed for InsForge: demo state can be
lost when its machine is replaced. Fixtures re-seed at process start.

## Render fallback

The user connects the repository through Render and creates a Blueprint using
`deploy/render.yaml` as its Blueprint path. This selects a paid starter service
and persistent disk; review the price before provisioning. Enter all `sync:
false` values in Render's secret settings. Deploy one replica. Redeploy through
Manual Deploy with the desired revision; roll back to the previous successful
release in the dashboard, or deploy that revision again. Image rollback does
not revert the persistent database; avoid incompatible schema changes.

## Release checks and limits

Check `/`, `/health`, and the full create-confirm-run-report journey on the HTTPS
URL, for example `BASE_URL=https://YOUR_HOST scripts/smoke.sh`. Public-mode
secure cookies require HTTPS. The smoke suite can hit public quotas because it
polls run status and repeats idempotent requests; a 429 should be assessed
against the guard limits rather than treated as an application regression.
Run the unrestricted full suite locally, and a paced create-confirm-run-report
journey on the public host. Supply operator credentials privately only if
operator update checks are intended. Check session caps: five creates, three runs, two agent evaluations.
Exceeding them gives a versioned 429 error and `Retry-After`. Invalid attempts
also consume budget. Model routes share an hourly process budget of 60 attempts.
IP requests are limited to 60 per minute, except health probes. Uvicorn defaults
to rejecting forwarded IP headers. Configure trusted proxy IPs only after
verifying the host's proxy topology; otherwise limits apply to the proxy IP.
Cookies can be reset by visitors, so session quotas alone are not authentication.

Coordinator integration: import `public_guard` and call `public_guard.install(app)`
immediately after `FastAPI(...)` creation, before the session-cookie middleware
decorator. Public cookies should also be `secure=True`. Verify guard behavior
before publishing. Do not expose real customer data or rely on this demo guard
as production authorization.
