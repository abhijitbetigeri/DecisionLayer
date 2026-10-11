# Decision Layer: demo runbook (4 minutes)

**Live:** https://decision-layer.onrender.com · **Repo:** github.com/abhijitbetigeri/DecisionLayer

**The one idea:** enterprise software websites make buyers (and their AI agents) do the
translation. Decision Layer turns a buyer's problem into an evidence-backed evaluation: it proves
what it can, says "unknown" where it can't, and updates when the evidence changes.

## Before you start (2 minutes)

1. Open the live URL about a minute early (the free instance sleeps when idle).
2. Render dashboard → service → **Environment** → copy `PROOFPATH_OPERATOR_TOKEN`.
3. Use **one fresh incognito window** for the whole demo. Each session is capped at 5 evaluations,
   3 proofs and 2 agent runs, and evaluation links only open in the browser that created them.
4. Have this brief ready to paste (it gives the clearest arc):

   > We need to sync NetSuite invoices and payments into Snowflake for our month-end close. Our data
   > must stay in the EU, and before we sign we need to see a failed sync recover without creating
   > duplicate records.

## The click path

| Time | Click | What the audience sees | Say |
|---|---|---|---|
| 0:00 | Homepage | Hero card: EU **Met**, SSO **Unknown**, a real citation | "This is a vendor site. Notice it already says what it can't prove: SSO is unknown." |
| 0:20 | Paste the brief → **Evaluate my use case** | Parsed requirements: EU hosting, recovery demonstrated | "Plain language in. An open model turns it into requirements, and the buyer confirms them before anything runs." |
| 0:40 | **Confirm** | Requirement matrix + **Decision progress**: *Needs verification*, next step "Run recovery verification" | "EU is documented. Recovery is only documented, and this buyer asked for proof. So: needs verification." |
| 1:00 | Toggle **Finance**, then back to **Technical** | Plan and cost view ($999 Business), same facts | "Different stakeholder, different emphasis. The facts never change." |
| 1:15 | Next steps → **Go to proof of concept** → **Prove it** | Live events: sync, injected failure, retry, exactly one record. 4 passes | "This is real code against labeled mock systems. It fails on purpose, retries with the same key, and we check there is exactly one record." |
| 1:50 | (automatic) | Recovery → **Demonstrated**. Badge → **Fit**. Timeline records it | "Documented became demonstrated, and the decision changed because of evidence, not copy." |
| 2:10 | **Comparison** section | FlowBridge vs RelayWorks vs PipeStack on the same requirements | "Same requirements for every vendor. PipeStack is US-only, so it's not a fit." |
| 2:25 | **Create report** | Frozen report link | "This decision record is frozen. You can send it to security or procurement." |
| 2:40 | Bottom → **Operator sign in** (paste token) → **Simulate competitor evidence update** | "Requires review" banner; nothing changes yet | "A competitor just changed their pricing page. Nothing changes until a human approves it." |
| 3:00 | **Approve** | RelayWorks EU moves to Enterprise (quote); comparison updated; timeline entry | "Approved, so the comparison updates. And the earlier report?" Open it: still Business $899. "Unchanged. History is preserved." |
| 3:25 | **Run buyer agent** | Open-weight model (gpt-oss-120b) returns a cited decision | "The same evidence is served to AI agents, with citations it must use." |
| 3:40 | **Visitor Lab** (top right) or the results slide | Homepage 62% vs Evaluation Workspace 100% correct | "Across four open-weight models, agents decided correctly 15 of 24 times from the homepage, and 24 of 24 from the workspace. This website builds an evaluation around your problem, runs the proof, and revises the decision when the evidence changes." |

## If something goes wrong

| Problem | Do this |
|---|---|
| Typed brief shows "Parsed by preset" | Models are off or keys missing. Use the **EU technical** preset chip and continue; the flow is identical. |
| Agent shows "Rule-based evaluation" | Same cause. Say: "When models are unavailable it says so instead of pretending." |
| "Session limit reached" (429) | Open a new incognito window. |
| You approved the update in rehearsal | Render dashboard → **Manual Deploy → Restart service** (no disk, so it reboots clean). |
| Site is slow on first load | It was asleep. Wait about 60 seconds. |
| Network fails entirely | Run locally: `PROOFPATH_OPERATOR_TOKEN=demo123 PROOFPATH_DEMO_MODE=stage uv run python -m uvicorn sv.proofpath.app:app --port 8001` |

## Likely judge questions

- **"Is the integration real?"** The proof runs real code with real failure, retry and idempotency
  checks against labeled local mocks. It does not claim certified Salesforce or Snowflake connectors.
- **"Who decides fit, the model?"** No. Models parse text, act as buyers and summarize. Fit
  decisions and test results are deterministic code.
- **"Where does Coframe fit?"** Coframe-style experiments can optimize the homepage copy and entry
  points, but toward `qualified_evaluation_completed` (a confirmed, evidence-backed evaluation)
  instead of clicks. Findings and decisions are never in an experiment slot.
- **"Is the 100% fair?"** Arm B serves structured, cited evidence plus the decision rule. It shows
  that serving evidence this way lets agents decide correctly; it is not a test of raw reasoning.
  3 of the homepage misses were model timeouts.
- **"Which models?"** Open-weight on cloud: Gemma 4 (parsing), gpt-oss-120b, Qwen3 235B, Kimi K2
  (buyer agents); Jev for fast yes/no checks.

## Don't

- Push to GitHub during judging (every push redeploys the site for a few minutes).
- Share workspace or report links with judges (they only open in your browser). Share the homepage.
