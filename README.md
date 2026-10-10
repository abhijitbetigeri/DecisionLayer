# Second Visitor

**Coframe makes websites better for human visitors. Second Visitor makes them work for the
other visitor, AI agents, without letting them lie.**

More than half of web traffic is now bots, and half of B2B software buyers start their
research in an AI chatbot. Buyer agents visit vendor sites to verify requirements (price at a
seat count, SSO, SOC 2, data residency). When a site is built for human eyes, the agent can't
verify, and the vendor silently drops off the shortlist. And when you let an AI optimize the
site for agents, the fastest win is to claim things that aren't true.

Second Visitor is a multi-agent wind tunnel for a website:

1. **Simulate**: buyer agents with personal briefs, across three model families, try to qualify the vendor.
2. **Diagnose**: each failure gets a named struggle (price hidden, content gated, requirement unstated).
3. **Fix**: a variant makes the same facts readable by agents.
4. **Guard**: every claim on every surface is checked against the source of truth, and contradictions are blocked.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and current results.

## Quick start

```bash
uv sync
# serve the demo site (variants at /A/, /C/, /D/)
uv run uvicorn sv.site.app:app --reload
# offline A/B test: variants x briefs x models x repeats
uv run python -m sv.simulator.run --variants A C D --n 2 --diagnose --exp my-exp
# guard: fact-check every surface of a variant
uv run python -m sv.guard C D
```

LLM calls go through the Respan gateway; credentials are read from `~/.respan/credentials.json`
or `RESPAN_API_KEY` (see `.env.example`).
