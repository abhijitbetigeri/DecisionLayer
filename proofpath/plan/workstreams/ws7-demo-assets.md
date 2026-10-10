# WS7: Demo assets: slides, diagram, video script (external agent)

**Time box: 60 minutes.** Goal: everything for the pitch except the live app and screen
recordings, so that when the build freezes, recording and editing take minutes.

**Read first:**
- `../README.md` (rules)
- `../demo-video.md` (live script, shot list)
- `../shared-truth.md` §0 (branding)
- `PLAN.md`, `ARCHITECTURE.md` (Visitor Lab results so far)
- `proofpath/README.md` intro (Decision Layer, Visitor Lab, Evaluation Workspace)

## Files you own

- `proofpath/demo/` (everything inside)
- Your status file: `proofpath/plan/status/ws7.md`

## Deliverables

1. **Three slides max** (`proofpath/demo/slides/`). Use the Artifact tool's Slides type if
   available, otherwise a single self-contained HTML deck. Match the FlowBridge/Decision Layer look
   (read `sv/proofpath/static/tokens.css` once WS3 has shipped it; do not edit it).
   1. **Problem:** "Enterprise software websites make buyers do the translation", plus the agent-traffic fact
      (more than half of web traffic is now bots; half of B2B buyers start research in AI chatbots, G2 2026).
   2. **How it works:** the architecture diagram (below).
   3. **Results:** Visitor Lab numbers (placeholder until `runs/proofpath-summary.json` exists),
      plus the existing Pulse reward-hack table from `ARCHITECTURE.md` (the D variant lies →
      shortlist rate up, correctness down → guard blocks it).
2. **Architecture diagram** (`proofpath/demo/architecture.svg` + `.png`):
   - Coframe-style optimization loop → Evaluation Workspace (brief → walkthrough → POC → compare → report)
     → Visitor Lab engine (simulator, guard, oracle), with open-weight models on cloud
   - Must read in both light and dark backgrounds.
3. **Voiceover script** (`proofpath/demo/voiceover.md`):
   - timed to the shot list in `demo-video.md`, 2:30-3:00 total
   - plain sentences, zero em-dashes
   - also a 60-second cut
4. **Captions file** (`proofpath/demo/captions.srt`) from the voiceover.
5. **Title and end cards** (`proofpath/demo/cards/`, 1920×1080 PNG):
   - title: "Decision Layer: evidence-driven enterprise software evaluation"
   - end: repo path / URL placeholder, team names placeholder
6. **Results chart generator** (`proofpath/demo/make_chart.py`):
   - reads `runs/proofpath-summary.json` and writes `proofpath/demo/visitor-lab.png`
     (homepage vs Evaluation Workspace correct-decision rate, with 95% intervals and n)
   - use the `dataviz` skill guidance

## Rules

Never edit code under `sv/`, templates or static files. No invented numbers: placeholders stay
labeled until real results exist. Use the real Pulse numbers from `ARCHITECTURE.md`.
