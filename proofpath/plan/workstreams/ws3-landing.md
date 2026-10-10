# WS3: FlowBridge landing page (built with taste-skill) + design tokens

**Time box: 70 minutes (tokens.css within 15).** User-facing names per shared-truth §0 (Decision Layer, Evaluation Workspace).

**Goal:** the first thing judges see. A FlowBridge homepage that looks like a real, premium B2B
product (not AI slop), and turns into an evaluation when the buyer states their problem. You also
own the design tokens the workspace (WS4) reuses.

**Before writing any markup, invoke the `design-taste-frontend` skill** (installed globally from
`leonxlnx/taste-skill`) and follow it. Then read `../shared-truth.md` §1 and §6 and
`../../README.md` section "Homepage and workspace".

## Files you own

- `sv/proofpath/templates/_base.html`
- `sv/proofpath/templates/home.html`
- `sv/proofpath/static/tokens.css`
- `sv/proofpath/static/home.css`
- `sv/proofpath/static/home.js`
- `sv/proofpath/static/img/`

## First 30 minutes: ship `static/tokens.css`

All token names from shared-truth §6, in light and dark (`prefers-color-scheme`, page-level lock),
then notify the coordinator so WS4 can theme against it. Pick one accent that is not AI-purple;
status colours must pass contrast and pair with icons.

## Design direction (taste-skill applied)

- **Design read:** "Reading this as: B2B SaaS landing for enterprise technical buyers and their
  agents, with a trust-first, Linear-clean language, leaning toward Tailwind v4 utilities + Geist +
  restrained motion."
- **Dials:** `DESIGN_VARIANCE 6 / MOTION_INTENSITY 4 / VISUAL_DENSITY 4`.
- **Stack, adapted to the no-build constraint:** Tailwind v4 via `@tailwindcss/browser` CDN,
  `@phosphor-icons/web` CDN (one icon family, consistent weight), Geist + Geist Mono with
  `font-display: swap`, CSS transitions plus small vanilla JS. No React, no npm build.
- **Copy:** use the README's hero copy: "Connect your systems. Automate your business."
  Nav: Product, Integrations, Enterprise, Pricing.

## Page structure (README content, taste-skill layout rules)

1. **Nav:** single line, ≤ 72px.
2. **Hero:**
   - max 4 text elements: headline, subtext ≤ 20 words, primary CTA "Evaluate my use case", secondary "Book a demo"
   - fits the first viewport (`min-h-[100dvh]`, `pt` ≤ 24)
   - **Hero visual: a real component preview, not a div-faked screenshot.** A live mini
     requirement matrix rendered from the actual `eu_technical` example payload
     (`examples/workspace.json`), with Met/Unknown states and a citation, so the hero shows the
     product truthfully.
3. **Evaluation input** directly under the hero:
   - large text area prefilled with the demo brief
   - three preset chips (EU technical, US operations, Strict budget)
   - submit → `POST /api/v1/evaluations` → redirect to `/evaluations/{id}`
   - visible loading and failure states
4. **Features** (prebuilt connectors, workflow builder, reliable execution, enterprise controls):
   an asymmetric bento with exactly 4 cells, **not 3 equal cards**, with at least 2 cells
   visually varied.
5. **Pricing:**
   - Team $299 / Business $999 / Enterprise "Talk to us"
   - capabilities rendered **from fixture facts only**, so SSO never appears as included
   - **no SSO or SOC 2 badge**; use the link "Review security evidence" instead
6. **Trust / security section:** "Review security evidence" leads into the workspace evidence view.
   Illustrative only, with the fictional label.
7. **Agent strip:** one line for agents: "Agents: read this evaluation at `/api/v1/...agent-context`".
   Also add `<link rel="alternate" type="application/json">` and an `llms.txt` route
   request to the coordinator.
8. **Footer:** the fictional label (shared-truth §1).

## Coframe-ready markup (no SDK work here)

Wrap only approved presentation regions in `data-cf-slot="hero-copy|primary-cta|entry-point|walkthrough-intro"`.
Findings, test outcomes, citations and decision fields are never inside a slot. WS5 wires the adapter.

## Taste-skill pre-flight (must pass before reporting done)

- zero em-dashes or en-dash separators anywhere visible
- eyebrows ≤ 1 per 3 sections
- no 3-equal-card row, no div-based fake screenshot, no AI-purple, no pure black, no neon glow
- no decorative status dots, no scroll cue, no version labels
- one theme lock; mobile collapse declared per section; `prefers-reduced-motion` respected
- copy self-audit done: no filler verbs ("seamless", "elevate"), no invented precise numbers
- logos (if any) are invented-brand monograms, not text wordmarks

## Done when

- `/` renders in light and dark at 375px, 768px and 1280px with no horizontal scroll.
- Submit works against the stub API.
- The hero preview renders from the example JSON.
- The pre-flight list above is checked off in your report.

## Phase 0 is done: what exists now

- `sv/proofpath/contracts.py`: frozen types (import these, never redefine).
- `sv/proofpath/repository.py`: `Repository(path)`; use `Repository(":memory:")` in tests. Raises
  `ConflictError` (HTTP 409) and `NotFoundError` (HTTP 404).
- `sv/proofpath/app.py`: every route is live. Routes call **your functions below** if your module
  exists; otherwise they serve `sv/proofpath/examples/*.json` with `"stub": true`.
- Stub workspace for UI work: `/evaluations/11111111-1111-4111-8111-111111111111`.
- Run: `uv run uvicorn sv.proofpath.app:app --port 8001`. Tests: `uv run pytest tests/proofpath -q`.
- Events: append with `repo.append_event(Event(evaluation_id=..., run_id=..., type=EventType.X, payload={...}))`.
  The app already emits `brief_parsed`, `brief_confirmed`, `workspace_generated`, `poc_queued`,
  `report_created` and `agent_evaluation_finished`, so do not emit those yourself.

## Functions the app calls (frozen signatures)

The home route renders `templates/home.html` with context `{demo_mode, operator}`. Submit with
`fetch('/api/v1/evaluations', {method:'POST', body: JSON.stringify({brief_text, preset_id})})` →
`data.evaluation_id` → `location = '/evaluations/' + id`. In stub mode the id is the example id, which works.
The hero preview reads `/static/...` or fetches `/api/v1/evaluations/11111111-1111-4111-8111-111111111111/workspace` (stub);
after integration it uses a seeded showcase. Ask the coordinator for a `/api/v1/showcase` route if you need one.
