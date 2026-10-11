# Decision Layer: architecture and tech stack

**Live:** https://decision-layer.onrender.com · **Repo:** https://github.com/abhijitbetigeri/DecisionLayer

Decision Layer has two modules that share one set of facts, requirements and decision rules:

- **Evaluation Workspace** (`sv/proofpath/`): turns a buyer's problem into an evidence-backed
  evaluation. It parses the brief, checks each requirement against cited evidence, runs a real proof
  of concept, compares vendors, freezes decision records, and gates evidence updates behind human review.
- **Visitor Lab** (`sv/`): a multi-agent simulator that measures whether buyers' AI agents reach
  correct decisions, plus a claim guard that blocks site variants that lie.

The demo uses fictional vendors (FlowBridge, RelayWorks, PipeStack) and real machinery: real model
calls, a real executable proof of concept, and real measured agent results.

## Architecture

```
         ┌──────────────────── VISITOR LAB (measures it all) ────────────────────┐
         │  4 open models act as buyers: homepage text vs workspace evidence     │
         │  Result: 15/24 correct (62%) vs 24/24 correct (100%)                  │
         └───────────────────────────────────────────────────────────────────────┘
                                         │ checks
 BUYER ──► FlowBridge homepage ──► Evaluation Workspace ───────────────► Decision record
 (human        (vendor site,         brief → evidence → proof →          (frozen report,
  or agent)     Coframe-style         comparison → update                 shareable)
                optimizable)
```

### End-to-end flow

| # | Buyer does | System does | Who decides |
|---|---|---|---|
| 1 | Lands on the FlowBridge homepage | Hero shows a live requirement card from a real seeded evaluation (EU Met, SSO Unknown, with a citation). Agents find `/llms.txt` and an agent endpoint | Code (from evidence) |
| 2 | Types a brief or picks a preset | Gemma 4 maps the text to an allowlist of requirements (EU/US hosting, SSO, demonstrated recovery, no duplicates, budget). Anything else is flagged "not recognized". Model failure falls back to a labeled preset | Model proposes, code validates |
| 3 | Confirms the requirements | Brief version is locked. Nothing is evaluated before confirmation; edits create a new version and mark old conclusions stale | Buyer |
| 4 | Reads the requirement matrix and Decision progress | Each vendor × requirement is Met / Unmet / Unknown, with basis (Documented / Demonstrated), plan and citation. Rule: any verified unmet hard requirement → Not a fit; any unknown → Needs verification; else Fit | Deterministic code |
| 5 | Toggles Technical ↔ Finance | Same facts, different emphasis | Presentation only |
| 6 | Clicks **Prove it** | A background worker runs `crm_warehouse_sync/v1`: mock CRM → sync → mock warehouse. Record 2 fails on purpose, retries with the same idempotency key, and a re-delivery leaves exactly one record. 4 assertions, 30 s deadline, cleanup, live events | Deterministic tests |
| 7 | Watches the decision change | Recovery moves Documented → Demonstrated; decision recomputes (e.g. Needs verification → Fit); timeline and next steps update | Code |
| 8 | Reads the comparison | All vendors on the same confirmed requirements: hard constraints first, then preference score and coverage (null-safe) | Code |
| 9 | Creates a report | Freezes a full copy of the brief, comparison snapshot, test results and citations | Code |
| 10 | (Operator) simulates a competitor update | New source version is created as pending; Jev screens it for hidden AI instructions; affected evaluations show "Requires review" | Human gate |
| 11 | (Operator) approves | Evaluations recompute; `comparison_updated` is logged; the earlier report stays unchanged | Human approves, code recomputes |
| 12 | Runs the buyer agent | gpt-oss-120b (fallback Qwen3 235B, then a labeled rule-based result) reads only the agent endpoint, must cite real claim or test ids, and is scored against the correct decision | Model answers, code scores |
| 13 | Opens Visitor Lab | Shows measured homepage vs workspace agent accuracy | Measured |

### Cross-cutting rules

- **Events:** every action is appended to an ordered event log, which powers the live timeline.
- **Isolation:** evaluations belong to the browser session that created them; operator actions need a token.
- **Measurement:** a Coframe-style optimizer would target `qualified_evaluation_completed`
  (confirmed brief, no unresolved hard requirements, current evidence) instead of clicks.
- **Honesty:** fictional labels on every page, mock systems named as mocks, no model ever decides
  fit or test outcomes, and unknown stays unknown.

## Tech stack

### Core app

| Technology | How it is used | Where |
|---|---|---|
| **Python** | All application logic: evaluation engine, POC runner, agents, simulator | `sv/` |
| **FastAPI** | Web server and API: pages and `/api/v1/...` routes, session middleware, operator auth, startup hook that seeds fixtures and starts the POC worker | `sv/proofpath/app.py` |
| **Jinja** | Server-rendered HTML for the homepage, workspace and frozen report; no frontend build step | `sv/proofpath/templates/` |
| **Tailwind CSS** | Styling via Tailwind v4's in-browser build (CDN), mapped to shared design tokens in light and dark; Phosphor icons and Geist fonts via CDN | `templates/_base.html`, `static/tokens.css` |
| **Pydantic** | Frozen data contracts shared by every module (briefs, claims, findings, POC runs, reports, events); validates API bodies and model output | `sv/proofpath/contracts.py` |
| **SQLite** | (1) App database: evaluations, brief versions, evidence versions, runs, frozen reports, ordered events. (2) Inside the POC, a fresh per-run table is the "Snowflake stand-in" checked for exactly one record | `repository.py`, `poc/adapter.py` |

### Models (cloud-hosted, open-weight first)

| Technology | How it is used | Where |
|---|---|---|
| **OpenRouter** (via the **Respan** gateway) | Routes every open-weight model call through one OpenAI-compatible key | `sv/llm.py` |
| **Gemma 4 31B** | Parses typed briefs into requirements; one of four simulated buyers | `requirements.py`, `sim_bridge.py` |
| **gpt-oss-120b** | Live buyer agent behind "Run buyer agent"; simulated buyer | `agent.py`, `sim_bridge.py` |
| **Qwen3 235B** | Fallback buyer agent; simulated buyer | `agent.py`, `sim_bridge.py` |
| **Kimi K2** | Fallback brief parser; simulated buyer | `requirements.py`, `sim_bridge.py` |
| **Vercel AI Gateway → Jev** (TypeSafe) | Fast yes/no decisions (~130 ms): screens evidence updates for injected AI instructions, checks model-written summaries against evidence. Never used for numbers or dates | `sv/jev.py`, `evidence.py`, `agent.py` |

Models parse, summarize and act as buyers. They never approve claims, change test results or decide fit.

### Build, test, deploy

| Technology | How it is used | Where |
|---|---|---|
| **uv** | Dependencies and lockfile; runs every command; installs locked deps in Docker | `pyproject.toml`, `uv.lock` |
| **pytest** | 93 tests: 14-case expected-decision matrix, POC lifecycle (retry, cancel, timeout, cleanup), report immutability, session isolation, agent citation checks | `tests/proofpath/` |
| **Playwright** | Headless Chromium verification of the full browser journey, console errors, phone width and dark mode, locally and against the live site (not part of the product) | `scripts/browser_acceptance.py` |
| **Docker** | Container image: Python 3.12 slim, locked deps, non-root user, health check | `Dockerfile` |
| **Render** | Hosting: builds the Dockerfile from GitHub on every push via the Blueprint; API keys are dashboard-only secrets | `render.yaml` |

### Supporting libraries

| Library | How it is used |
|---|---|
| **BeautifulSoup** | Converts the homepage into the text an agent sees, for Visitor Lab's homepage arm |
| **httpx** | HTTP client for Jev calls |
| **OpenAI Python SDK** | Client for the OpenAI-compatible Respan gateway |

## Repository map

```
sv/proofpath/          Evaluation Workspace
  app.py               FastAPI routes, auth, showcase, worker wiring
  contracts.py         frozen Pydantic contracts (schema v1)
  repository.py        SQLite persistence and transactions
  requirements.py      brief parsing (Gemma 4 → Kimi K2 → preset) and validation
  evidence.py          fixtures, source versions, pending update, review, Jev screen
  evaluation.py        findings, decision rule, workspace projection
  comparison.py        hard constraints, preference score, coverage
  reports.py           immutable report snapshots
  poc/                 mock adapter and lifecycle-managed runner
  agent.py             buyer agent and agent-context
  telemetry.py         live / simulated / replay events
  sim_bridge.py        Visitor Lab homepage vs agent-context sweep
  public_guard.py      per-session and per-IP caps for the public demo
  templates/, static/  homepage (taste-skill), workspace, report
sv/                    Visitor Lab engine (simulator, oracle, guard, diagnose, Pulse benchmark)
proofpath/             product spec, multi-agent build plan, demo runbook and assets
tests/proofpath/       automated tests
render.yaml, Dockerfile  deployment
```
