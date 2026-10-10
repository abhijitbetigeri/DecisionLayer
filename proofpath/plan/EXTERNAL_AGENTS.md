# Additional implementation workstreams

WS6, WS7, and WS8 were launched through the assistant's available collaboration tools in this
session. The terminal prompts below remain an alternative for future sessions; do not launch
duplicate agents for workstreams that are active or complete. Read each workstream's status file
first. The collaboration tools run assistant agents, not separate Claude Code terminal sessions.

Open a **new Claude Code session** for each workstream below, in the repo folder:

```bash
cd ~/projects/decision-layer && claude
```

Paste the matching prompt. Each workstream owns separate files, so the sessions can run at the same
time as the coordinator and the five in-session subagents (WS1-WS5) without conflicts.

| Workstream | Who runs it | Owns | Needs from you |
|---|---|---|---|
| WS0 coordinator + integration | **this session (main)** | `sv/proofpath/app.py`, `contracts.py`, `repository.py`, `auth.py`, `worker.py`, `pyproject.toml`, `uv.lock` | nothing |
| WS1-WS5 | subagents of this session (already running) | see `README.md` ownership map | nothing |
| **WS6 deploy** | **your extra agent #1** | `Dockerfile`, `.dockerignore`, `deploy/`, `scripts/deploy.sh`, `sv/proofpath/public_guard.py` | maybe a Railway/Render login if InsForge compute access is gated; pasting secrets into the host dashboard |
| **WS7 demo assets** | **your extra agent #2** | `proofpath/demo/` | team names for the end card |
| **WS8 QA** | **your extra agent #3** | `tests/proofpath/test_api_journey.py`, `test_isolation.py`, `scripts/smoke.sh`, `scripts/demo_reset.sh`, `proofpath/ACCEPTANCE.md` | nothing |

Each extra agent writes progress and asks to `proofpath/plan/status/<ws>.md` (its own file), and
the coordinator reads those files. Don't let extra agents edit `proofpath/plan/README.md` (the
coordinator's status board).

---

## Prompt for extra agent #1 (WS6 deploy)

```
You are WS6 (public deployment) on the Decision Layer hackathon project in this repo, working in
parallel with other agents. Time box 60 minutes.
Read, in order: proofpath/plan/workstreams/ws6-deploy.md (your brief), proofpath/plan/README.md
(rules for parallel work), proofpath/plan/deployment.md.
Edit ONLY the files your brief says you own. Never edit sv/proofpath/app.py or other agents' files,
pyproject.toml or uv.lock (ask the coordinator via your status file). Never read or print .env. Do not
commit or push. Do not create accounts or paste secrets yourself: ask me.
Log progress, blockers and your final report in proofpath/plan/status/ws6.md.
Start by checking whether InsForge compute is available for my account (use the insforge-cli skill).
```

## Prompt for extra agent #2 (WS7 demo assets)

```
You are WS7 (demo assets) on the Decision Layer hackathon project in this repo, working in parallel
with other agents. Time box 60 minutes.
Read, in order: proofpath/plan/workstreams/ws7-demo-assets.md (your brief), proofpath/plan/README.md,
proofpath/plan/demo-video.md, proofpath/plan/shared-truth.md section 0, ARCHITECTURE.md.
Edit ONLY files under proofpath/demo/ and your status file proofpath/plan/status/ws7.md. Never edit
code, templates or static files. No invented numbers: keep placeholders labeled until
runs/proofpath-summary.json exists. Zero em-dashes in any visible text. Do not commit or push.
Log progress and your final report in proofpath/plan/status/ws7.md.
```

## Prompt for extra agent #3 (WS8 QA)

```
You are WS8 (QA, smoke tests, acceptance) on the Decision Layer hackathon project in this repo,
working in parallel with other agents who are still building the modules you test. Time box 60 minutes.
Read, in order: proofpath/plan/workstreams/ws8-qa.md (your brief), proofpath/plan/README.md,
proofpath/plan/integration.md, proofpath/plan/shared-truth.md section 4, sv/proofpath/contracts.py,
sv/proofpath/app.py, sv/proofpath/examples/.
Edit ONLY the files your brief says you own. Never edit application modules; report bugs in
proofpath/plan/status/ws8.md with the failing test name. Use port 8018 and temp data dirs only.
Never read .env. Do not commit or push. Tests must skip (not fail) when a module is not built yet.
Log progress and your final report in proofpath/plan/status/ws8.md.
```
