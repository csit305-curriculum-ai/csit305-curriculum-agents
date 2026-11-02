"""Replay loader for the demo (no network, no LLM calls).

Reads REAL recorded outputs from runs/ and the committed freeze manifest. Never invents output:
if nothing was recorded for a task/condition, it returns None and the app shows "no recorded run".
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DIRS = ["smoke_2", "smoke"]  # newest first
TEST001_DIR = "test001_science"


def recorded_results(root: Path = ROOT) -> dict[tuple[str, str], list[dict]]:
    """(task_id, condition) -> list of recorded results, newest run dir first.

    Uses the full local trace.jsonl (MoE text, git-ignored) when present, otherwise the committed summary.csv
    (status/tokens/cost only, no lesson text)."""
    out: dict[tuple[str, str], list[dict]] = {}
    for d in RUN_DIRS:
        rd = root / "runs" / d
        trace, summ = rd / "trace.jsonl", rd / "summary.csv"
        if trace.exists():
            for line in trace.read_text().splitlines():
                r = json.loads(line)
                if r.get("event") == "result":
                    r["_source"] = f"runs/{d}/trace.jsonl"
                    out.setdefault((r["task_id"], r["condition"]), []).append(r)
        elif summ.exists():
            with summ.open() as f:
                for r in csv.DictReader(f):
                    r["_source"] = f"runs/{d}/summary.csv (no lesson text: full trace is kept locally only)"
                    r["output"] = None
                    out.setdefault((r["task_id"], r["condition"]), []).append(r)
    return out


def test001_rows(root: Path = ROOT) -> list[dict]:
    p = root / "runs" / TEST001_DIR / "test001_results.csv"
    if not p.exists():
        return []
    with p.open() as f:
        return list(csv.DictReader(f))


def frozen_hash(task_id: str, root: Path = ROOT) -> str | None:
    """Frozen packet hash: local packets/<id>.json first, else the committed freeze_manifest.json."""
    p = root / "packets" / f"{task_id}.json"
    if p.exists():
        return json.loads(p.read_text()).get("bundle_hash")
    m = root / "packets" / "freeze_manifest.json"
    if m.exists():
        return json.loads(m.read_text()).get("packets", {}).get(task_id, {}).get("bundle_hash")
    return None


C_OFFLINE_DIR = "c_offline"


def c_offline_run(task_id: str, root: Path = ROOT) -> dict | None:
    """Latest offline/scripted Condition C job for a task: {'job': result, 'nodes': [node_result...]}.
    Full trace (local only) when present, else the committed summary.csv row (no node trace, no text)."""
    rd = root / "runs" / C_OFFLINE_DIR
    trace, summ = rd / "trace.jsonl", rd / "summary.csv"
    if trace.exists():
        recs = [json.loads(l) for l in trace.read_text().splitlines()]
        jobs = [r for r in recs if r.get("event") == "result" and r["task_id"] == task_id and r["condition"] == "C"]
        if jobs:
            job = jobs[-1]
            nodes = [r for r in recs if r.get("event") == "node_result" and r["run_id"] == job["run_id"]]
            return {"job": job, "nodes": nodes, "_source": f"runs/{C_OFFLINE_DIR}/trace.jsonl"}
    if summ.exists():
        with summ.open() as f:
            rows = [r for r in csv.DictReader(f) if r["task_id"] == task_id and r["condition"] == "C"]
        if rows:
            return {"job": dict(rows[-1], output=None, nodes=[]), "nodes": [], "_source": f"runs/{C_OFFLINE_DIR}/summary.csv"}
    return None


def test001_c_rows(root: Path = ROOT) -> list[dict]:
    p = root / "runs" / (TEST001_DIR + "_c") / "test001_results.csv"
    if not p.exists():
        return []
    with p.open() as f:
        return list(csv.DictReader(f))
