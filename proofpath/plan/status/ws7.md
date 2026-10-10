# WS7 demo assets

State: complete; PNG, SVG, HTML, scripts and captions verified.

## Completed

- Three-slide self-contained HTML deck in `proofpath/demo/slides/index.html`.
- Decision Layer branding with Visitor Lab and Evaluation Workspace.
- Existing Pulse reward-hack figures faithfully transcribed with n, intervals, and caveats.
- Primary-source links for G2 buyer research and Imperva automated traffic, with dates and scope.
- Three-minute voiceover, sixty-second cut, and SRT captions.
- Editable title/end-card and architecture scene generator.
- Real-result chart generator using `sim_bridge` summary schema (`results.A`, `results.B`).
- Missing results and stub-context checks prevent fabricated headline metrics.
- All implementation files confined to `proofpath/demo/` and this status file.

## Verification

- `python3 -m py_compile proofpath/demo/make_chart.py proofpath/demo/build_assets.py`: passed.
- `python3 proofpath/demo/make_chart.py`: expected exit 2, results unavailable. No numbers invented.
- `rg -n '—' proofpath/demo`: no em-dashes.
- `python3 proofpath/demo/build_assets.py`: passed with native CoreGraphics renderer.
- PNG headers checked: title, end and architecture all 1920 x 1080.
- Architecture and title PNG visually inspected: legible, unclipped, brand-consistent.
- SVG XML parsing, Wilson interval boundaries, SRT monotonic timestamps (0 to 180 seconds): passed.

## Remaining inputs and integration

- User must provide team names and final repository/public URL before end-card export.
- Screen recordings and voice recording need the completed running app; this workstream does not fabricate video.
- Real Visitor Lab summary required before new results/chart can be shown.
- Deck currently labels the new benchmark RESULTS PENDING; omit it if C4 is not run.
- Pillow install unavailable due restricted network; generators use standard Python plus macOS CoreGraphics/CoreText instead. No dependency or lockfile edits.
- No commits, environment-file reads, application-code edits, or changes to existing runs.
