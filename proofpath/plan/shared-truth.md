# Shared truth: every agent reads this first

If code disagrees with this file, the code is wrong. Changes go through the coordinator.

## 0. Branding

- Platform: **Decision Layer**, tagline "Evidence-driven enterprise software evaluation."
- Modules: **Visitor Lab** (can humans and agents reach accurate decisions from the site) and
  **Evaluation Workspace** (requirements, walkthrough, POC, comparison).
- The fictional vendor site is **FlowBridge**; its evaluation flow shows "Evaluation Workspace by
  Decision Layer". Never show "ProofPath" or "Second Visitor" in the UI.

## 1. Labels that must always be visible

- Site-wide footer and workspace header: **"Fictional products and evidence; live tests use local
  mock integrations."**
- POC panel: **"Demo sandbox: mock CRM and warehouse stand-ins, no real Salesforce or Snowflake."**
- Rule-based fallback: **"Rule-based evaluation"** (never "AI agent").
- Replay mode: **"Recorded replay"** badge.
- Coframe: not integrated in this build (no real project). Do not show any Coframe badge or claim.

## 2. Requirement keys (the allowlist)

| key | label | kind | satisfied by |
|---|---|---|---|
| `eu_hosting` | EU deployment | capability | documented claim with plan applicability |
| `us_hosting` | US deployment | capability | documented claim |
| `sso` | Single sign-on (SAML) | capability | documented claim |
| `recovery_demonstrated` | Failed syncs recover without duplicates, **demonstrated** | demonstration | a passing POC run of `crm_warehouse_sync/v1` (documented support alone is NOT enough) |
| `idempotent_delivery` | No duplicate records on retry, documented | capability | documented claim or a passing POC |
| `budget_monthly_usd` | Monthly budget ceiling | constraint | the cheapest plan meeting all capability requirements has a known price ≤ value; a quote-only plan makes it `unknown` |

Model-parsed briefs may only contain these keys. Anything else is dropped and shown to the user as
"not recognized, add manually".

## 3. Fixture facts (seeded, approved at seed time)

| Product | Plans and monthly price | EU | US | SSO | Recovery / idempotency |
|---|---|---|---|---|---|
| **FlowBridge** | Team $299; Business $999; Enterprise quote | documented on Business, Enterprise | documented, all plans | **no claim** (so `unknown`) | documented (Business+); demonstrable by POC |
| **RelayWorks v1** | Business $899 | documented on Business | documented | documented on Business | documented only, no independent run |
| **PipeStack** | Business $699 | **documented US-only** (so EU `unmet`) | documented | documented | no claim (`unknown`) |

**Controlled update** (pending until operator approves): **RelayWorks v2**: EU moves to
Enterprise-only, Enterprise is quote-only (price unknown). SSO and recovery unchanged.

## 4. Presets and expected decisions (encode as tests in Phase 0)

Decision rule (README): any verified `unmet` hard requirement → `not_fit`; else any `unknown` or
contradicted hard requirement → `needs_verification`; else `fit`. Preferences never override.

**Preset `eu_technical`.** Hard: `eu_hosting`, `sso`, `recovery_demonstrated`. Preferences: implementation effort, connector coverage.

| Product | Before POC | After FlowBridge POC passes | After RelayWorks v2 approved |
|---|---|---|---|
| FlowBridge | needs_verification (SSO unknown, recovery not yet demonstrated) | **needs_verification** (SSO still unknown) | unchanged |
| RelayWorks | needs_verification (recovery not demonstrated) | unchanged | needs_verification; EU now Enterprise-only, cost explanation changes |
| PipeStack | **not_fit** (EU unmet) | unchanged | unchanged |

**Preset `us_operations`.** Hard: `us_hosting`, `recovery_demonstrated`. Preference: `sso`.

| Product | Before POC | After FlowBridge POC passes |
|---|---|---|
| FlowBridge | needs_verification | **fit** |
| RelayWorks | needs_verification | unchanged |
| PipeStack | needs_verification | unchanged |

**Preset `strict_budget`.** Hard: `eu_hosting`, `budget_monthly_usd ≤ 900`, `recovery_demonstrated`.

| Product | Before | After RelayWorks v2 approved |
|---|---|---|
| FlowBridge | **not_fit** (EU needs Business at $999 > $900) | unchanged |
| RelayWorks | needs_verification ($899 fits, recovery not demonstrated) | needs_verification; budget now `unknown` (quote), never "confirmed budget fit" |
| PipeStack | not_fit (EU unmet) | unchanged |

**Demo brief text** (maps to `eu_technical`): "We need to sync Salesforce opportunities into
Snowflake, require EU hosting and SSO, and need failed syncs to recover without duplicate records."

## 5. Models (cloud, open-weight first; all verified 2026-10-10)

All through `sv/llm.py` (Respan gateway) except Jev (`sv/jev.py`, Vercel AI Gateway).

| Use | Primary | Fallback chain |
|---|---|---|
| Brief text → requirement keys | `openrouter/google/gemma-4-31b-it` | `openrouter/moonshotai/kimi-k2` → preset/guided form |
| Cited summary of findings (optional) | `openrouter/google/gemma-4-31b-it` | deterministic template |
| Buyer agent on stage | `openrouter/openai/gpt-oss-120b` | `openrouter/qwen/qwen3-235b-a22b-2507` → "Rule-based evaluation" |
| Buyer-agent population (simulator) | gpt-oss-120b, qwen3-235b-a22b-2507, kimi-k2, gemma-4-31b-it | add `claude-haiku-4-5-20251001` only for comparison |
| Fast decisions: injection screen on source updates, claim-supported checks | Jev `typesafe-ai/jev` | gemma-4-31b-it |

**Never:** DeepSeek (user decision), Llama 4 Maverick, gpt-oss-20b, Qwen3-Next (broken tool calls).
No model approves claims, changes test results, or decides fit. Record model id, input version and
cited ids for every model call.

## 6. Design tokens (WS3 owns `static/tokens.css`; WS4 consumes it)

**Design read (taste-skill §0.B):** "Reading this as: B2B SaaS landing for enterprise technical
buyers and their agents, with a trust-first, Linear-clean language, leaning toward Tailwind v4
utilities + Geist + restrained motion."

**Dials:** `DESIGN_VARIANCE: 6`, `MOTION_INTENSITY: 4`, `VISUAL_DENSITY: 4` (trust-first B2B,
between the "SaaS landing" and "regulated" presets).

**Stack constraint:** no frontend build. Tailwind v4 via `@tailwindcss/browser` CDN, Phosphor icons
via `@phosphor-icons/web` CDN, Geist + Geist Mono self-hosted or via CDN with `font-display: swap`,
motion in CSS and small vanilla JS (`prefers-reduced-motion` respected).

**Token names** (values chosen by WS3, both light and dark): `--bg`, `--surface`, `--surface-2`,
`--text`, `--text-muted`, `--border`, `--accent`, `--accent-text`, and status colours that must be
distinguishable without colour alone: `--status-met`, `--status-unmet`, `--status-unknown`,
`--status-demonstrated`, plus `--radius`, `--shadow-1`, `--font-sans`, `--font-mono`.

**Status vocabulary in UI:** Met, Unmet, Unknown (finding); Documented, Demonstrated, Unknown,
Contradicted (evidence); each with an icon and a text label, never colour alone.
