"""Internal funnel telemetry and replay export (WS5). Coframe is not integrated in this build.

Internal events: brief_confirmed, poc_started, poc_completed, report_created,
qualified_evaluation_completed. Every record carries a channel, and live, simulated and replay
records are stored and counted separately so agent runs and replays never inflate live metrics.

Storage: the frozen EventType enum has no `poc_completed` or `qualified_evaluation_completed`, and
the app/runner already emit the domain events, so telemetry records live in the repository's meta
table (`telemetry:<evaluation_id>` list + `telemetry_counts:<channel>` counters) rather than as
duplicate domain events. `channel_counts` also counts domain events by `Event.channel`.

  uv run python -m sv.proofpath.telemetry export <evaluation_id> [--out runs/proofpath-replay-<id>.jsonl]
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from sv.proofpath.contracts import FindingStatus, ReviewStatus
from sv.proofpath.repository import NotFoundError

NAMES = ("brief_confirmed", "poc_started", "poc_completed", "report_created",
         "qualified_evaluation_completed")
CHANNELS = ("live", "simulated", "replay")
REPLAY_BADGE = "Recorded replay"


def _key(evaluation_id: str) -> str:
    return f"telemetry:{evaluation_id}"


def _load(repo, key: str, default):
    raw = repo.get_meta(key)
    return json.loads(raw) if raw else default


def record(repo, evaluation_id: str, name: str, channel: str = "live") -> None:
    if name not in NAMES:
        raise ValueError(f"unknown telemetry event {name!r}")
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    with repo.transaction():
        log = _load(repo, _key(evaluation_id), [])
        log.append({"name": name, "channel": channel, "ts": time.time()})
        repo.set_meta(_key(evaluation_id), json.dumps(log))
        counts = _load(repo, f"telemetry_counts:{channel}", {})
        counts[name] = counts.get(name, 0) + 1
        repo.set_meta(f"telemetry_counts:{channel}", json.dumps(counts))


def events(repo, evaluation_id: str, channel: Optional[str] = None) -> list[dict]:
    log = _load(repo, _key(evaluation_id), [])
    return [e for e in log if channel is None or e["channel"] == channel]


def counters(repo, channel: str = "live") -> dict[str, int]:
    """Global per-channel counters. Metrics read 'live' only."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    return {n: _load(repo, f"telemetry_counts:{channel}", {}).get(n, 0) for n in NAMES}


def channel_counts(repo, evaluation_id: str) -> dict[str, dict[str, int]]:
    """Domain events (Event.channel) and telemetry records for one evaluation, split by channel."""
    out = {c: {} for c in CHANNELS}
    for c, n in Counter((e.channel, e.type.value) for e in repo.list_events(evaluation_id)).items():
        out.setdefault(c[0], {})[c[1]] = n
    for e in events(repo, evaluation_id):
        bucket = out.setdefault(e["channel"], {})
        bucket[f"telemetry.{e['name']}"] = bucket.get(f"telemetry.{e['name']}", 0) + 1
    return out


# ------------------------------------------------------------------ qualification milestone
def is_qualified(repo, evaluation_id: str) -> bool:
    """Confirmed current brief, no unresolved hard constraint for FlowBridge, evidence current."""
    try:
        ev = repo.get_evaluation(evaluation_id)
    except NotFoundError:
        return False
    if not ev.current_brief_version_id:
        return False
    brief = repo.get_brief(ev.current_brief_version_id)
    if brief.confirmed_at is None:
        return False
    snap = repo.latest_comparison(evaluation_id)
    if snap is None or snap.brief_version_id != brief.id:
        return False                                            # comparison is stale
    if any(s.review_status == ReviewStatus.pending for s in repo.list_source_versions()):
        return False                                            # evidence review outstanding
    for sid in snap.source_version_ids:
        try:
            if repo.get_source_version(sid).review_status != ReviewStatus.approved:
                return False
        except NotFoundError:
            return False
    vendor = next((p for p in snap.products if p.product_id == "flowbridge"), None)
    if vendor is None:
        return False
    hard = {r.id for r in brief.requirements if r.hard}
    hard_findings = [f for f in vendor.findings if f.requirement_id in hard]
    if len({f.requirement_id for f in hard_findings}) < len(hard):
        return False
    return all(f.status == FindingStatus.met for f in hard_findings)


def qualified_evaluation_completed(repo, evaluation_id: str) -> bool:
    """True when the milestone holds; records it once on the live channel."""
    if not is_qualified(repo, evaluation_id):
        return False
    if not any(e["name"] == "qualified_evaluation_completed" for e in events(repo, evaluation_id, "live")):
        record(repo, evaluation_id, "qualified_evaluation_completed", "live")
    return True


# ------------------------------------------------------------------ replay export
SENSITIVE_PAYLOAD_KEYS = {"brief_text", "content", "token", "session_id", "email"}


def export_replay(repo, evaluation_id: str, out: Path) -> int:
    """Sanitized JSONL of one evaluation's events, re-labeled channel=replay. Returns line count."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} exists; replay exports never overwrite")
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w") as f:
        for e in repo.list_events(evaluation_id):
            payload = {k: v for k, v in e.payload.items() if k not in SENSITIVE_PAYLOAD_KEYS}
            f.write(json.dumps({"sequence": e.sequence, "type": e.type.value, "run_id": e.run_id,
                                "payload": payload, "channel": "replay", "original_channel": e.channel,
                                "created_at": e.created_at.isoformat(), "badge": REPLAY_BADGE}) + "\n")
            n += 1
        for t in events(repo, evaluation_id):
            f.write(json.dumps({"type": "telemetry", "name": t["name"], "channel": "replay",
                                "original_channel": t["channel"], "badge": REPLAY_BADGE}) + "\n")
            n += 1
    return n


def load_replay(path: Path) -> list[dict]:
    """Replay records for display. Always channel=replay; never feed these into live counters."""
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    for r in rows:
        r["channel"] = "replay"
        r["badge"] = REPLAY_BADGE
    return rows


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Evaluation Workspace telemetry tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="export a sanitized replay JSONL of one evaluation")
    ex.add_argument("evaluation_id")
    ex.add_argument("--db", default=None, help="path to proofpath.db (default: $PROOFPATH_DATA_DIR)")
    ex.add_argument("--out", default=None)
    a = p.parse_args(argv)
    import os
    from sv.proofpath.repository import Repository
    db = a.db or str(Path(os.environ.get("PROOFPATH_DATA_DIR", ".proofpath-data")) / "proofpath.db")
    out = Path(a.out or f"runs/proofpath-replay-{a.evaluation_id[:8]}-{int(time.time())}.jsonl")
    n = export_replay(Repository(db), a.evaluation_id, out)
    print(f"wrote {n} replay records to {out}")


if __name__ == "__main__":
    main()
