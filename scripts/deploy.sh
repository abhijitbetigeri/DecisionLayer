#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-check}"
case "$mode" in
  check)
    docker build -t decision-layer:local .
    docker run --rm --entrypoint python decision-layer:local -c 'from sv.proofpath.app import app; from sv.proofpath.public_guard import install; print(app.title)'
    ;;
  insforge)
    : "${DEPLOY_ENV_FILE:?Set DEPLOY_ENV_FILE to a private host secret file outside this repository}"
    npx @insforge/cli compute deploy . --name decision-layer --port 8080 --cpu shared-1x --memory 512 --env-file "$DEPLOY_ENV_FILE"
    ;;
  *) echo 'Usage: scripts/deploy.sh [check|insforge]' >&2; exit 2 ;;
esac
