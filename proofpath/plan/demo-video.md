# Demo pieces and video

## Demo assets to produce

| Asset | Source | Owner | When |
|---|---|---|---|
| Live app (homepage → workspace → POC → update → agent → report) | the build | all | Phase 2 |
| Operator view (approve/reject update) | WS4 operator session | WS4 | C2 |
| **Headline number:** agents' correct decisions, homepage text vs `agent-context` | `sim_bridge` summary JSON | WS5 | C4 |
| **Reward-hack slide:** Pulse D lies → shortlist up, correctness down, guard blocks | existing `runs/ab-2` | coordinator | any time |
| Architecture diagram (Coframe loop → Evaluation Workspace → Visitor Lab engine) | PLAN.md mermaid, cleaned | coordinator | Phase 3 |
| Recorded replay file | replay export | WS5 | after final rehearsal |
| Submission video (2:30-3:00) | screen recording + voiceover | coordinator + user | Phase 3 |
| 3 slides max: problem, how it works, results | Slides artifact or HTML | coordinator | Phase 3 |

## Four-minute live script (from the README, with exact lines)

| Time | On screen | Say |
|---|---|---|
| 0:00-0:30 | FlowBridge homepage, light theme | "Enterprise software websites make buyers do the translation. What if the website could demonstrate whether the product fits?" |
| 0:30-1:30 | Paste the demo brief → confirm requirements → workspace appears; switch Technical ↔ Finance | "It parsed four requirements. EU is documented. SSO is **unknown**, and we say so instead of guessing. Switching to the finance view changes emphasis, never the facts." |
| 1:30-2:30 | Click "Prove it": live events, injected failure, retry, exactly one record | "This is real code against mock systems, clearly labeled. The adapter fails on purpose, retries with the same idempotency key, and we assert there is exactly one record. Recovery moves from Documented to **Demonstrated**." |
| 2:30-3:20 | Operator: "Simulate competitor evidence update" → review → approve; diff + "Comparison updated"; open the earlier report | "RelayWorks just moved EU hosting to Enterprise-only. Nothing changes until a human approves it. After approval the comparison updates, and the earlier report stays exactly as it was." |
| 3:20-4:00 | Run buyer agent (gpt-oss-120b) → cited "needs verification"; flash the agent numbers | "The same evidence is served to agents. An open-weight agent reads it and reaches the right call, with citations. Across four open models, agents decided correctly X% from the homepage and Y% through Evaluation Workspace. This website builds an evaluation around your problem, runs the proof, and revises the decision when the evidence changes." |

**Judge-specific beats (one sentence each, only if asked):**
- Coframe: "Your loop can optimize for `qualified_evaluation_completed` instead of clicks."
- Glasp/Hashiri: "Every claim carries a source, a date and a status, and unknown stays unknown."

## Submission video (2:30-3:00)

**Recording:** QuickTime screen recording (or `ffmpeg -f avfoundation`) at 1920×1080, browser at
125% zoom, light theme, notifications off. Record each scene as a separate take. Voiceover
recorded separately, so retakes are cheap.

**Shot list:**
1. (0:00-0:12) Title card: "Decision Layer: a website that proves product fit, for buyers and their agents."
2. (0:12-0:35) Problem: homepage, then the Pulse reward-hack table ("optimizing for agents without a guard makes sites lie").
3. (0:35-1:10) Brief → workspace → requirement matrix close-up on "SSO: Unknown".
4. (1:10-1:45) Prove it: live events, retry, "exactly one record", Demonstrated.
5. (1:45-2:15) Evidence update: pending → approve → diff → old report unchanged.
6. (2:15-2:40) Agent: gpt-oss-120b cited decision + agent-numbers chart.
7. (2:40-2:55) Architecture slide: Coframe loop → Evaluation Workspace → Visitor Lab engine; open-weight models on cloud.
8. (2:55-3:00) End card: repo/URL, team.

**Editing:**
- cut and assemble with the `video-edit` skill (ffmpeg); burn in captions from the voiceover script
- no music under speech
- export H.264 1080p, under 100 MB
- make a 60-second cut from shots 3, 4 and 6 for social posts

## Rehearsal

- Two full timed run-throughs on a freshly reset app, one of them on the replay fallback.
- Assign who drives and who talks.
- Note the exact click path and keep the operator tab pre-authenticated.
- Freeze the build after the final rehearsal: no code changes in the last 30 minutes.
