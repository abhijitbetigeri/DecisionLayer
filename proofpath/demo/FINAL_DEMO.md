# Decision Layer final demo

## Start and verify

Run `PROOFPATH_ENABLE_LLM=0 uv run python -m uvicorn sv.proofpath.app:app --host 127.0.0.1 --port 8001` for a dependable rule-based demo. Supply an operator token through the environment to enable source updates. Never put the token in a slide or recording. Enable model execution separately only after testing access.

- Homepage: `http://127.0.0.1:8001/`
- Visitor Lab: `http://127.0.0.1:8001/visitor-lab`
- Tests: `PROOFPATH_ENABLE_LLM=0 uv run pytest tests/proofpath -q`
- Real Chrome acceptance: `uv run --with playwright python scripts/browser_acceptance.py` (installed Chrome; temp data; port 8021).
- Record the verified journey: `uv run --with playwright python scripts/browser_acceptance.py --record`. Install its encoder first if needed: `uv run --with playwright python -m playwright install ffmpeg`.

The recording command produces `proofpath/demo/recordings/decision-layer-walkthrough.webm` and screenshots of each buyer path, evidence update, and Visitor Lab. These generated artifacts are excluded from Git. The video is a labeled automated walkthrough of actual local execution with rule-based evaluation; it is a visual fallback, not a narrated four-minute submission. Use `--output /path/to/artifacts` to select another directory. No real customer data or credentials appear in the recording.

## Four-minute story

1. **0:00–0:35, Visitor Lab:** Show baseline website versus structured evidence correctness. Display actual counts and intervals. Explain this is a small offline agent measurement, not human conversion lift. Missing results are labeled unavailable rather than substituted.
2. **0:35–1:35, successful fit:** Return home, choose US operations, submit, confirm, and click Prove it. Watch actual test assertions. The decision timeline shows recovery changing from unknown to demonstrated and FlowBridge becoming Fit.
3. **1:35–2:30, honest uncertainty:** Create EU technical evaluation. Confirm and run the POC. Recovery is demonstrated, but SSO remains unknown. Show the Next steps panel, its owner, and copyable SSO evidence request. Nothing is sent automatically.
4. **2:30–3:30, living evidence:** Create a report before the update. Sign in as operator; simulate the labeled RelayWorks source update, review, then approve. The timeline shows the plan/price changes. Open the prior report to show that its evidence remains frozen.
5. **3:30–4:00, shared truth:** Run the buyer evaluation and inspect citations. Rule-based fallback is visibly labeled. Close with: “A living website that adapts to your requirements, produces proof, and explains why the decision changed.”

## How the improvements work

- `/api/v1/evaluations/{id}/insights` computes deterministic history from stored comparison snapshots and proposes actions from unresolved hard requirements.
- Timeline evidence links resolve to evaluation-owned source versions or authorized run details. Old sources remain inspectable.
- Primary next steps focus on FlowBridge; competitor gaps remain in the comparison. Pending source changes are surfaced for review without becoming approved truth.
- `/api/v1/visitor-lab/results` reads the recorded summary, validates provenance/counts, and recomputes percentages and Wilson intervals. Opening the page does not start model calls.

## Finish checklist

Use fictional labels throughout. Check desktop/mobile and finance/technical views. Test one successful and one uncertain evaluation. Use the generated labeled screen recording for network failure. Final team names, public URL, and narrated submission edit remain release inputs.

Do not spend the final minutes adding connectors or broad crawling. Freeze the working journey, capture the recording, and rehearse once within four minutes.
