# Decision Layer submission voiceover

Target: 3:00. Record each scene separately. Timings include pauses for the UI.

| Time | Shot | Voiceover |
|---|---|---|
| 0:00-0:12 | Title card | Decision Layer is evidence-driven enterprise software evaluation. Its two modules, Visitor Lab and Evaluation Workspace, help buyers and their agents understand and verify product fit. |
| 0:12-0:35 | Homepage, then Pulse results | Enterprise software websites make buyers do the translation. Optimizing for more shortlists can even reward false claims. In our existing Pulse benchmark, the misleading variant had the highest shortlist rate. Our guard blocked its contradicted claims. These are offline agent results, not human conversion measurements. |
| 0:35-1:10 | Brief, confirmation, matrix, persona | Here is FlowBridge, a fictional integration vendor. Our buyer needs EU hosting, SSO, and a workflow that recovers without duplicate records. The buyer confirms the requirements before the workspace evaluates them. EU hosting is documented. SSO is unknown. We preserve that uncertainty. Switching to the finance view changes the emphasis while keeping the same facts. |
| 1:10-1:45 | Live POC events | Now we click Prove it. This executes real code against local mock CRM and warehouse systems. It injects a temporary failure and retries using the same idempotency key. The assertions check successful delivery, failure recovery, and exactly one destination record. A passing run demonstrates this bounded scenario. It does not certify the real vendor, and SSO still needs verification. |
| 1:45-2:15 | Operator review, diff, previous report | Next we simulate a competitor source update. RelayWorks moves EU hosting to a quote-only Enterprise plan. The change stays pending until an operator approves it. After approval, the comparison explains the new plan restriction and uncertain cost. The earlier report remains frozen, so the buyer can inspect what changed. |
| 2:15-2:40 | Buyer evaluation, citations, optional chart | The same approved evidence is available to a buyer agent. Its output includes citations, and the application checks its decision against deterministic rules. For this EU brief, the correct answer remains needs verification. When cloud inference is unavailable, the screen explicitly says Rule-based evaluation. Across four open-weight models, agents reading the homepage chose correctly 15 of 24 times. Reading the Evaluation Workspace, 24 of 24. Error bars are 95 percent intervals. |
| 2:40-2:55 | Architecture | Presentation experiments lead into the Evaluation Workspace. Visitor Lab checks whether agents reach accurate decisions. Evidence, test outcomes, and decision rules stay grounded as the interface and source material change. Coframe integration is a future connection, not a shipped claim. |
| 2:55-3:00 | End card | Decision Layer. A living website that demonstrates product fit. |

## Optional measured results insertion

Only after `runs/proofpath-summary.json` exists with `stub_context=false`, generate the chart.
Replace the last sentence of scene 6 with the actual arm A and B percentages, sample sizes,
and note that the error bars are 95% Wilson intervals. Do not read X and Y placeholders aloud.
If results do not exist, keep the current method explanation and omit the chart.

## 60-second cut

| Time | Shot | Voiceover |
|---|---|---|
| 0:00-0:08 | Brief input | Decision Layer turns a complex SaaS website into an evaluation built around the buyer's requirements. |
| 0:08-0:21 | Requirement matrix | This fictional buyer needs EU hosting, SSO, and reliable recovery. The workspace distinguishes documented facts from unknowns. Changing the stakeholder view keeps those facts consistent. |
| 0:21-0:37 | POC events | Prove it runs real code against local mock systems. We inject a failure, retry with the same key, and verify exactly one record. This demonstrates the bounded recovery scenario. |
| 0:37-0:48 | Approved update and history | An operator approves a simulated competitor update. The comparison changes, while the previous report stays frozen. |
| 0:48-0:56 | Cited buyer decision | Buyers and agents receive the same evidence. Unknown SSO means the decision remains needs verification. |
| 0:56-1:00 | End card | Decision Layer. Evidence-driven enterprise software evaluation. |

## Recording checks

- Keep fictional-product and local-mock labels visible.
- Show an actual passing test, not an animation presented as execution.
- If the agent is unavailable, narrate the labeled rule-based fallback.
- Keep the operator session prepared without showing credentials.
- Fill the repository URL and team names before exporting the final video.
- No claim of Coframe integration, production security certification, or verified real vendor comparison.
