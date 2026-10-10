# Decision Layer demo kit

Open `slides/index.html` directly in a browser. It is a self-contained three-slide deck
with offline styling; architecture.svg is the only local image dependency.
Use Left/Right arrow keys or the navigation buttons. Print to PDF if needed.

## Assets

- `voiceover.md`: three-minute submission narration, sixty-second cut, recording checks.
- `captions.srt`: timed captions matching the three-minute narration.
- `architecture.svg` and `architecture.png`: optimization, evaluation, and measurement flow.
- `cards/title.png`, `cards/end.png`: 1920 x 1080 video cards, with editable SVG counterparts.
- `build_assets.py`: regenerate cards and diagram from deterministic scene definitions.
- `make_chart.py`: generate a measured chart from `runs/proofpath-summary.json`.
- `render_macos.py`: offline macOS CoreGraphics/CoreText PNG renderer, no third-party dependencies.

```bash
python3 proofpath/demo/build_assets.py
python3 proofpath/demo/make_chart.py
```

The chart writes `visitor-lab.png` and `visitor-lab.svg`. Missing results and stub contexts
are rejected. The chart recomputes 95% Wilson intervals from actual success counts, reports
sample sizes and errors, and does not modify runs/. For another platform, SVG generation
works without macOS using `--svg-only`; PNG rendering currently requires macOS.

## Before submission

1. Replace team and repository/live URL placeholders in `build_assets.py`; regenerate cards.
2. Run the completed app, record the shot list, and distinguish cloud agents from rule-based fallback.
3. Run Visitor Lab on the completed evaluation context. Generate its chart only from genuine results.
4. Replace the pending-results banner on slide 3 with verified measurements, or retain it and omit the chart.
5. Record voiceover, combine the screen captures, and burn captions during video editing.

## Evidence and scope

Pulse slide figures are transcribed from ARCHITECTURE.md, ab-2, n=30 per variant.
They are an existing separate benchmark, not new FlowBridge results. Intervals overlap.
The deck makes no claim of statistically significant lift or human conversion improvement.

The problem slide cites primary sources: G2's March 2026 survey of 1,076 B2B software
buyers and Imperva's 2025 report covering 2024 traffic. The bot-traffic statistic includes
all automated traffic, not only AI purchasing agents. These contextual statistics are
separate from our own experiments.

Coframe-style optimization is a conceptual connection. Coframe is not integrated.
Products and evidence are fictional; POC code uses local mock integrations.
