"""Run conditions A/B for tasks. Usage:
  python -m cagents.run --tasks G3M-P1 --conditions A B --repeats 1 --out runs/smoke [--mock]
Retrieval is done once per task; the frozen bundle is saved and reused for every repeat (Doc 3 ARCH 002)."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml

from .conditions import TraceLogger, run_condition
from .retrieval import ROOT


def load_tasks(ids: list[str] | None) -> list[dict]:
    doc = yaml.safe_load((ROOT / "tasks.yaml").read_text())
    tasks = doc["tasks"]
    return [t for t in tasks if not ids or t["task_id"] in ids]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--conditions", nargs="+", default=["A", "B"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--out", default="runs/latest")
    ap.add_argument("--mock", action="store_true", help="use MockClient (no API calls)")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    logger = TraceLogger(out / "trace.jsonl")
    from .retrieval import BGEM3Embedder, Index
    idx = Index(BGEM3Embedder())
    if a.mock:
        from .llm import MockClient
        client = MockClient([json.dumps({"status": "insufficient_evidence", "grade": 3, "subject": "maths", "reason": "mock"})] * 100)
    else:
        from .llm import DeepSeekClient
        client = DeepSeekClient()
    rows = []
    for t in load_tasks(a.tasks):
        bundle = idx.retrieve(t["topic"], t["subject"], t["grade"], outcome_id=t.get("outcome_id"))
        (out / f"bundle_{t['task_id']}.json").write_text(bundle.to_json())
        for cond in a.conditions:
            for rep in range(1, a.repeats + 1):
                r = run_condition(t, cond, client, logger, bundle=bundle if cond == "B" else None, repeat=rep)
                rows.append({k: r.get(k) for k in ("run_id", "task_id", "condition", "repeat", "status", "attempts",
                             "total_prompt_tokens", "total_completion_tokens", "total_latency_s", "total_cost_usd", "reason")}
                            | {"bundle_hash": (r.get("bundle_hash") or "")[:16], "n_chunks": len(r.get("chunk_ids") or [])})
                print(rows[-1])
    with (out / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
