"""Visitor Lab measurement for the Evaluation Workspace: can buyer agents reach the right decision?

  uv run python -m sv.proofpath.sim_bridge --n 2 --exp first
  uv run python -m sv.proofpath.sim_bridge --presets eu_technical --models openrouter/openai/gpt-oss-120b --n 1

Arm A: the buyer agent reads the FlowBridge homepage as fetched text (GET /, no JS, via the
         simulator's page_to_text), and may follow same-site links.
Arm B: the buyer agent reads GET /api/v1/evaluations/{id}/agent-context (structured facts + ids).

Both arms use the same bounded tool loop and submit_decision tool as the on-stage agent
(sv/proofpath/agent.py). Correct = matches the expected FlowBridge decision (shared-truth §4).
The app is driven in-process with TestClient against a throwaway PROOFPATH_DATA_DIR. Events go to
runs/proofpath-<exp>.jsonl (sv/events.py style, all channel="simulated"); the summary the report
and demo slide read goes to runs/proofpath-summary.json. Rates carry n and 95% Wilson intervals.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from sv.proofpath import agent as A

RUNS = Path(__file__).resolve().parents[2] / "runs"
PRESETS = ("eu_technical", "us_operations", "strict_budget")

# Buyer briefs as the buyer would state them (shared-truth §4). Used for Arm A, where the agent has
# no structured brief from the workspace.
PRESET_BRIEFS = {
    "eu_technical": {
        "goal": "Sync Salesforce opportunities into Snowflake.",
        "hard": {"eu_hosting": "EU deployment available",
                 "sso": "Single sign-on (SAML)",
                 "recovery_demonstrated": "Failed syncs recover without duplicate records, demonstrated "
                                          "by a passing test run (documentation alone is not enough)"},
        "preferences": ["low implementation effort", "connector coverage"]},
    "us_operations": {
        "goal": "Sync Salesforce opportunities into Snowflake for US operations.",
        "hard": {"us_hosting": "US deployment available",
                 "recovery_demonstrated": "Failed syncs recover without duplicate records, demonstrated "
                                          "by a passing test run (documentation alone is not enough)"},
        "preferences": ["Single sign-on (SAML)"]},
    "strict_budget": {
        "goal": "Sync Salesforce opportunities into Snowflake on a strict budget.",
        "hard": {"eu_hosting": "EU deployment available",
                 "budget_monthly_usd": "The cheapest plan that meets the other hard requirements costs at "
                                       "most $900 per month (a quote-only price counts as unknown)",
                 "recovery_demonstrated": "Failed syncs recover without duplicate records, demonstrated "
                                          "by a passing test run (documentation alone is not enough)"},
        "preferences": []},
}

OPEN_URL_TOOL = {"type": "function", "function": {
    "name": "open_url",
    "description": "Fetch another page on the FlowBridge website (same site only) and return its readable text.",
    "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}

SYSTEM_HOMEPAGE = """You are a procurement agent acting for a buyer. Decide whether the vendor
FlowBridge fits the buyer's brief by reading its website only. The homepage text is below; you may
open other same-site pages with open_url. You have at most {max_turns} model turns.

Buyer brief (JSON):
{brief}

Decision rule: any hard requirement that the website shows is unmet -> not_fit; otherwise any hard
requirement you cannot verify from the website -> needs_verification; otherwise fit. Preferences
never override hard requirements. Report requirement_statuses (met | unmet | unknown) for every hard
requirement key, then call submit_decision. Use an empty citations list if the site has no ids.

HOMEPAGE TEXT (GET /, no JavaScript):
{page}"""


# ------------------------------------------------------------------ app driver
class AppDriver:
    """In-process app with its own data dir. Import sv.proofpath.app only after setting the env."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or tempfile.mkdtemp(prefix="proofpath-sim-")
        os.environ["PROOFPATH_DATA_DIR"] = self.data_dir
        if "sv.proofpath.app" in sys.modules and not os.environ.get("PROOFPATH_SIM_ALLOW_LOADED_APP"):
            raise RuntimeError("sv.proofpath.app already imported; sim_bridge needs a fresh data dir")
        from fastapi.testclient import TestClient
        from sv.proofpath.app import app
        self.client = TestClient(app)
        self.client.__enter__()            # run lifespan (seed fixtures, start worker)
        self.client.get("/")               # obtain the session cookie like a browser would
        self._lock = threading.Lock()
        self._pages: dict[str, str] = {}

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    def page_text(self, path: str) -> str:
        from sv.simulator.pagetext import page_to_text
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            return "error: same-site paths only, e.g. /pricing"
        if path.startswith("/api/") or path.startswith("/operator"):
            return "error: Arm A agents read the website only"
        with self._lock:
            if path not in self._pages:
                r = self.client.get(path)
                ctype = r.headers.get("content-type", "")
                if r.status_code != 200:
                    self._pages[path] = f"HTTP {r.status_code}"
                elif ctype.startswith("text/html"):
                    self._pages[path] = page_to_text(r.text)
                else:
                    self._pages[path] = r.text[:8000]
            return self._pages[path]

    def preset_context(self, preset_id: str) -> tuple[dict, bool]:
        """Create + confirm an evaluation for a preset; return (agent-context, stub?)."""
        with self._lock:
            r = self.client.post("/api/v1/evaluations", json={"brief_text": "", "preset_id": preset_id})
            body = r.json()
            stub = bool(body.get("stub"))
            data = body["data"]
            eid, brief = data["evaluation_id"], data["brief"]
            c = self.client.post(f"/api/v1/evaluations/{eid}/confirm", json={"brief_version_id": brief["id"]})
            stub = stub or bool(c.json().get("stub"))
            g = self.client.get(f"/api/v1/evaluations/{eid}/agent-context")
            gb = g.json()
            stub = stub or bool(gb.get("stub"))
            return gb["data"], stub


# ------------------------------------------------------------------ arms
def run_arm_a(driver: AppDriver, preset: str, model: str, *, chat: Optional[Callable] = None) -> dict:
    brief = PRESET_BRIEFS[preset]
    system = SYSTEM_HOMEPAGE.format(max_turns=A.MAX_TURNS, brief=json.dumps(brief, indent=2),
                                    page=driver.page_text("/"))
    pages = ["/"]

    def handle(name: str, args: dict) -> str:
        if name != "open_url":
            return f"error: unknown tool {name}"
        path = str(args.get("url", "/"))
        if "://" in path:                       # absolute URL: keep only the path on this site
            path = urlparse(path).path or "/"
        elif not path.startswith("/"):
            path = "/" + path
        pages.append(path)
        return driver.page_text(path)

    args, turns = A.run_tool_loop(model, system, "Evaluate FlowBridge against the brief.",
                                  [OPEN_URL_TOOL, A.SUBMIT_TOOL], handle, chat=chat)
    out = A.validate_submission(args, {"claims": [], "test_results": []}, list(brief["hard"]))
    expected = A.EXPECTED_FLOWBRIDGE[(preset, False)]
    return {"decision": out["decision"].value, "expected": expected.value,
            "correct": out["decision"] == expected, "turns": turns, "pages": pages,
            "requirement_statuses": {k: v.value for k, v in out["requirement_statuses"].items()},
            "citations": [], "rejected_citations": out["rejected_citations"]}


def run_arm_b(ctx: dict, preset: str, model: str, *, chat: Optional[Callable] = None) -> dict:
    out, turns = A.ask_model(model, ctx, chat=chat)
    expected = A.expected_decision(ctx, preset)
    return {"decision": out["decision"].value, "expected": expected.value,
            "correct": out["decision"] == expected, "turns": turns,
            "requirement_statuses": {k: v.value for k, v in out["requirement_statuses"].items()},
            "citations": out["citations"], "rejected_citations": out["rejected_citations"]}


# ------------------------------------------------------------------ sweep
def _wilson(k: int, n: int) -> tuple[float, float]:
    from sv.simulator.run import wilson        # reuse the engine's interval
    return wilson(k, n)


def summarize(rows: list[dict]) -> dict:
    by = defaultdict(lambda: {"k": 0, "n": 0, "errors": 0})
    for r in rows:
        for key in (r["arm"], f"{r['arm']}|{r['preset']}", f"{r['arm']}|{r['model']}"):
            b = by[key]
            b["n"] += 1
            b["k"] += int(bool(r.get("correct")))
            b["errors"] += int(r.get("error") is not None)
    out = {}
    for key, b in sorted(by.items()):
        lo, hi = _wilson(b["k"], b["n"])
        out[key] = {"correct": b["k"], "n": b["n"], "rate": round(b["k"] / b["n"], 3) if b["n"] else 0.0,
                    "wilson95": [round(lo, 3), round(hi, 3)], "errors": b["errors"]}
    return out


def sweep(presets, models, n: int, exp: str, *, workers: int = 8, chat: Optional[Callable] = None,
          driver: Optional[AppDriver] = None, runs_dir: Path = RUNS) -> dict:
    from sv.events import EventLog
    log_path = runs_dir / f"proofpath-{exp}.jsonl"
    if log_path.exists():
        raise FileExistsError(f"{log_path} exists; pick a new --exp (existing runs/ files are never modified)")
    runs_dir.mkdir(parents=True, exist_ok=True)
    if runs_dir == RUNS:
        log = EventLog(f"proofpath-{exp}")
    else:                                          # tests: write to a temp dir
        log = EventLog.__new__(EventLog)
        log.path = log_path
    own_driver = driver is None
    driver = driver or AppDriver()
    try:
        contexts = {p: driver.preset_context(p) for p in presets}
        driver.page_text("/")
        jobs = [(arm, p, m, seed) for p in presets for m in models for seed in range(n) for arm in ("A", "B")]
        rows: list[dict] = []

        def one(arm, preset, model, seed):
            run_id = uuid.uuid4().hex[:10]
            ctx, stub = contexts[preset]
            log.emit("run_started", run_id=run_id, variant=f"arm_{arm}", brief_id=preset, model=model,
                     seed=seed, channel="simulated", stub_context=stub)
            t0 = time.monotonic()
            try:
                res = run_arm_a(driver, preset, model, chat=chat) if arm == "A" else run_arm_b(ctx, preset, model, chat=chat)
                error = None
            except A.AgentFailure as e:
                res, error = {"decision": None, "correct": False, "turns": A.MAX_TURNS,
                              "expected": (A.EXPECTED_FLOWBRIDGE[(preset, False)] if arm == "A"
                                           else A.expected_decision(ctx, preset)).value}, str(e)
            row = {"run_id": run_id, "arm": arm, "preset": preset, "model": model, "seed": seed,
                   "stub_context": stub, "error": error, "seconds": round(time.monotonic() - t0, 2), **res}
            log.emit("run_finished", run_id=run_id, answer={"decision": res.get("decision"),
                     "requirement_statuses": res.get("requirement_statuses"), "citations": res.get("citations")},
                     truth=res.get("expected"), correct=res.get("correct"), shortlisted=None,
                     steps=res.get("turns"), error=error, channel="simulated",
                     rejected_citations=res.get("rejected_citations", []))
            return row

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(one, *j) for j in jobs]
            for f in as_completed(futs):
                row = f.result()
                rows.append(row)
                print(f"  arm {row['arm']} {row['preset']:<14} {row['model'].split('/')[-1]:<24} "
                      f"{str(row.get('decision')):<19} expected {row['expected']:<19} "
                      f"{'OK ' if row['correct'] else 'MISS'} {row['error'] or ''}", flush=True)
    finally:
        if own_driver:
            driver.close()

    summary = {
        "experiment": exp, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "channel": "simulated", "log": str(log_path.relative_to(runs_dir.parent)) if runs_dir == RUNS else str(log_path),
        "arms": {"A": "FlowBridge homepage as fetched text (GET /, no JS)",
                 "B": "GET /api/v1/evaluations/{id}/agent-context"},
        "presets": list(presets), "models": list(models), "n_per_cell": n,
        "stub_context": any(c[1] for c in contexts.values()),
        "metric": "correct-decision rate vs shared-truth §4 (FlowBridge), 95% Wilson interval",
        "results": summarize(rows),
        "invalid_citations_arm_b": sum(len(r.get("rejected_citations") or []) for r in rows if r["arm"] == "B"),
    }
    (runs_dir / "proofpath-summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Visitor Lab: Arm A (homepage text) vs Arm B (agent-context) "
                                            "correct-decision rates for FlowBridge.")
    p.add_argument("--presets", nargs="+", default=list(PRESETS), choices=PRESETS)
    p.add_argument("--models", nargs="+", default=list(A.POPULATION))
    p.add_argument("--n", type=int, default=2, help="repeats per preset x model x arm (default 2)")
    p.add_argument("--exp", default=time.strftime("%Y%m%d-%H%M%S"), help="experiment name for runs/proofpath-<exp>.jsonl")
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args(argv)
    for m in a.models:
        if m not in A.ALLOWED_MODELS or any(b in m.lower() for b in A.BANNED_FRAGMENTS):
            p.error(f"model {m} is not in the approved population (shared-truth §5)")
    if not A.llm_enabled():
        p.error("PROOFPATH_ENABLE_LLM=0: the simulator needs live models")
    s = sweep(a.presets, a.models, a.n, a.exp, workers=a.workers)
    print("\nArm  correct/n  rate   95% Wilson")
    for arm in ("A", "B"):
        r = s["results"].get(arm)
        if r:
            print(f"  {arm}   {r['correct']}/{r['n']}      {r['rate']:.2f}   [{r['wilson95'][0]:.2f}, {r['wilson95'][1]:.2f}]"
                  f"   errors={r['errors']}")
    if s["stub_context"]:
        print("NOTE: some contexts came from stubs (WS1 not landed); Arm B numbers are not meaningful yet.")
    print(f"log: {s['log']}  summary: runs/proofpath-summary.json")


if __name__ == "__main__":
    main()
