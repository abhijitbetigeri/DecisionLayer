# Decision Layer

**Evidence-driven enterprise software evaluation, for buyers and their AI agents.**

**Live demo:** https://decision-layer.onrender.com · **Repo:** https://github.com/abhijitbetigeri/DecisionLayer

Enterprise software websites make buyers do the translation. Decision Layer turns a vendor website
into a living evaluation: it turns a buyer's problem into requirements, checks each one against cited
evidence, runs a real proof of concept, compares vendors, and revises the decision when the evidence
changes, while keeping earlier decision records frozen.

- **Evaluation Workspace:** brief → requirement matrix → "Prove it" (real failure, retry, exactly one
  record) → comparison → frozen report → human-reviewed evidence updates → cited buyer-agent decision.
- **Visitor Lab:** measures whether AI agents reach correct decisions. Across four open-weight models,
  agents reading the vendor homepage decided correctly **15/24 (62%)**; reading the Evaluation
  Workspace agent endpoint, **24/24 (100%)**.

Fictional vendors (FlowBridge, RelayWorks, PipeStack), real machinery: real model calls, a real
executable proof of concept against labeled mock systems, and real measured agent results.

## Docs

| Doc | What's in it |
|---|---|
| [TECH_STACK.md](TECH_STACK.md) | Architecture, end-to-end flow, and how each technology is used |
| [proofpath/DEMO.md](proofpath/DEMO.md) | 4-minute demo runbook, recovery steps, judge Q&A |
| [proofpath/README.md](proofpath/README.md) | Product specification and hackathon implementation spec |
| [proofpath/plan/](proofpath/plan/README.md) | Multi-agent build playbook (workstreams, integration, deployment) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Visitor Lab engine and the Pulse reward-hack benchmark |

## Run locally

```bash
uv sync
PROOFPATH_OPERATOR_TOKEN=demo123 PROOFPATH_DEMO_MODE=stage \
  uv run python -m uvicorn sv.proofpath.app:app --port 8001
# open http://127.0.0.1:8001
```

Use `python -m uvicorn` (a system-wide `uvicorn` may not see the project's dependencies).

```bash
uv run pytest tests/proofpath -q                                   # 93 tests
uv run python -m sv.proofpath.sim_bridge --n 2 --exp my-run        # Visitor Lab sweep
```

## Configuration

| Variable | Purpose |
|---|---|
| `RESPAN_API_KEY` | Open-weight models via the Respan gateway (falls back to `~/.respan/credentials.json` locally) |
| `AI_GATEWAY_API_KEY` | Jev via Vercel AI Gateway |
| `PROOFPATH_OPERATOR_TOKEN` | Operator actions (approve or reject evidence updates, reset) |
| `PROOFPATH_ENABLE_LLM` | `0` disables model calls; the app falls back to presets and a labeled rule-based agent |
| `PROOFPATH_DEMO_MODE` | `local`, `stage` (slower POC steps for presenting) or `public` (usage caps on) |
| `PROOFPATH_DATA_DIR` | Where SQLite and run artifacts live (default `.proofpath-data/`) |

Secrets are never committed; on Render they are dashboard-only (`sync: false` in `render.yaml`).
