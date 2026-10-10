"""Offline A/B test: variants x briefs x models x repeats, scored against the oracle.

  uv run python -m sv.simulator.run --variants A C D --n 2 --exp first

Prints, per variant, the share of runs where the agent reached the correct decision and the
share where it kept Pulse on the shortlist, each with n and a 95% Wilson interval.
"""
from __future__ import annotations

import argparse
import itertools
import math
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from sv import llm
from sv.diagnose import diagnose_run
from sv.events import EventLog
from sv.facts import load_briefs, oracle, score
from sv.simulator.agent import run_agent


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def one_run(variant: str, brief: dict, model: str, seed: int, log: EventLog, diagnose: bool) -> dict:
    run_id = uuid.uuid4().hex[:10]
    log.emit("run_started", run_id=run_id, variant=variant, brief_id=brief["id"], model=model, seed=seed)
    truth = oracle(brief)
    try:
        answer, steps = run_agent(run_id=run_id, variant=variant, brief=brief, model=model, log=log)
        error = None if answer else "no_answer"
    except Exception as e:                     # a flaky model call is a failed run, not a crash
        answer, steps, error = None, 0, f"{type(e).__name__}: {e}"[:300]
    result = score(answer, truth) if answer else {"correct": False, "shortlisted": False}
    log.emit("run_finished", run_id=run_id, variant=variant, brief_id=brief["id"], model=model,
             answer=asdict(answer) if answer else None, truth=asdict(truth), steps=steps,
             error=error, **result)
    if diagnose and not result["correct"] and not error:
        diagnose_run(run_id, log)
    return {"variant": variant, "brief": brief["id"], "model": model, **result, "error": error}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=["A", "C", "D"])
    ap.add_argument("--briefs", nargs="+", default=None, help="brief ids (default: all)")
    ap.add_argument("--models", nargs="+", default=llm.BUYER_MODELS)
    ap.add_argument("--n", type=int, default=1, help="repeats per (variant, brief, model)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--exp", default="exp-" + uuid.uuid4().hex[:6])
    ap.add_argument("--diagnose", action="store_true", help="tag a struggle for each failed run")
    args = ap.parse_args()

    briefs = [b for b in load_briefs() if args.briefs is None or b["id"] in args.briefs]
    log = EventLog(args.exp)
    jobs = list(itertools.product(args.variants, briefs, args.models, range(args.n)))
    print(f"{len(jobs)} runs -> runs/{args.exp}.jsonl")

    results = []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(one_run, v, b, m, s, log, args.diagnose) for v, b, m, s in jobs]
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            mark = "✓" if r["correct"] else ("!" if r["error"] else "✗")
            print(f"  {mark} {r['variant']} {r['brief']:<20} {r['model']}" + (f"  {r['error']}" if r["error"] else ""))

    by_variant = defaultdict(list)
    for r in results:
        by_variant[r["variant"]].append(r)
    print(f"\n{'variant':<8}{'n':>4}  {'correct':>22}  {'shortlisted':>22}  errors")
    for v in args.variants:
        rs = by_variant[v]
        n = len(rs)
        c = sum(r["correct"] for r in rs)
        s = sum(r["shortlisted"] for r in rs)
        e = sum(bool(r["error"]) for r in rs)
        cl, ch = wilson(c, n)
        sl, sh = wilson(s, n)
        print(f"{v:<8}{n:>4}  {c/n:>6.0%} [{cl:.0%}-{ch:.0%}]{'':>6}  {s/n:>6.0%} [{sl:.0%}-{sh:.0%}]{'':>6}  {e}")


if __name__ == "__main__":
    main()
