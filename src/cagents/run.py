"""Freeze packets, then run conditions A/B. Usage:
  python -m cagents.run freeze [--tasks ...]
  python -m cagents.run run --tasks G3M-P1 --conditions A B --repeats 1 --out runs/smoke [--mock] [--seed 305]
Packets are retrieved once and frozen (Doc 3 Stage 2). Each timed B request repeats retrieval and must reproduce
the frozen packet; a mismatch stops the run. Condition order is randomised within each task x repeat block."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import uuid
from pathlib import Path

import yaml

from . import corpus
from .conditions import TraceLogger, run_condition
from .retrieval import ROOT, EvidenceBundle, assert_reproduces

PACKETS = ROOT / "packets"
SUMMARY_FIELDS = ["run_id", "job_id", "task_id", "split", "grade", "subject", "outcome_id", "condition", "repeat", "order_pos",
                  "status", "completion", "attempts", "generation_called", "word_count", "prompt_tokens", "completion_tokens",
                  "cached_tokens", "cost_usd", "retrieval_latency_s", "gen_latency_s", "total_latency_s", "requested_model",
                  "returned_model", "bundle_hash", "n_chunks", "corpus_hash", "reason"]


def load_tasks(ids: list[str] | None) -> list[dict]:
    doc = yaml.safe_load((ROOT / "tasks.yaml").read_text())
    d = doc.get("defaults", {})
    return [dict(d, **t) for t in doc["tasks"] if not ids or t["task_id"] in ids]


def _index():
    from .retrieval import BGEM3Embedder, Index
    return Index(BGEM3Embedder())


def freeze(ids: list[str] | None) -> None:
    corpus.verify_sources()
    idx = _index()
    PACKETS.mkdir(exist_ok=True)
    man = {"tasks_yaml_sha256": hashlib.sha256((ROOT / "tasks.yaml").read_bytes()).hexdigest(), "corpus_hash": idx.corpus_hash(),
           "packages": _freeze_pkgs(), "packets": {}}
    for t in load_tasks(ids):
        b = idx.retrieve(t["topic"], t["subject"], t["grade"], outcome_id=t.get("outcome_id"))
        (PACKETS / f"{t['task_id']}.json").write_text(b.to_json())
        man["packets"][t["task_id"]] = {"status": b.status, "bundle_hash": b.bundle_hash, "chunk_ids": b.chunk_ids, "reason": b.reason}
        print(t["task_id"], b.status, b.chunk_ids or b.reason)
    (PACKETS / "freeze_manifest.json").write_text(json.dumps(man, indent=1))


def _freeze_pkgs() -> list[str]:
    from importlib.metadata import distributions
    return sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions())


def run(a) -> None:
    corpus.verify_sources()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    logger = TraceLogger(out / "trace.jsonl")
    idx = _index() if "B" in a.conditions else None
    if a.mock:
        from .llm import MockClient
        client = MockClient([json.dumps({"status": "insufficient_evidence", "grade": 3, "subject": "maths", "reason": "mock"})] * 1000)
    else:
        from .llm import DeepSeekClient
        client = DeepSeekClient()
    rng = random.Random(a.seed)
    rows = []
    for t in load_tasks(a.tasks):
        frozen = None
        if "B" in a.conditions:
            fp = PACKETS / f"{t['task_id']}.json"
            if not fp.exists():
                raise SystemExit(f"No frozen packet for {t['task_id']}; run `python -m cagents.run freeze` first")
            frozen = EvidenceBundle.from_json(fp.read_text())
        for rep in range(1, a.repeats + 1):
            job_id = uuid.uuid4().hex[:12]
            order = list(a.conditions)
            rng.shuffle(order)
            for pos, cond in enumerate(order, 1):
                live = None
                if cond == "B":
                    live = idx.retrieve(t["topic"], t["subject"], t["grade"], outcome_id=t.get("outcome_id"))
                    assert_reproduces(frozen, live)  # raises PacketMismatch -> run stops
                r = run_condition(t, cond, client, logger, bundle=live, repeat=rep, job_id=job_id, order_pos=pos)
                last = {}
                for line in reversed((out / "trace.jsonl").read_text().splitlines()):
                    e = json.loads(line)
                    if e.get("run_id") == r["run_id"] and e.get("event") == "attempt":
                        last = e
                        break
                row = {k: r.get(k) for k in SUMMARY_FIELDS}
                row.update(returned_model=last.get("returned_model"), bundle_hash=(r.get("bundle_hash") or "")[:16],
                           n_chunks=len(r.get("chunk_ids") or []), corpus_hash=(r.get("corpus_hash") or "")[:16])
                rows.append(row)
                print({k: row[k] for k in ("task_id", "condition", "status", "attempts", "prompt_tokens", "completion_tokens", "cost_usd", "word_count")})
    with (out / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader(); w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--tasks", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("--tasks", nargs="*"); r.add_argument("--conditions", nargs="+", default=["A", "B"])
    r.add_argument("--repeats", type=int, default=1); r.add_argument("--out", default="runs/latest")
    r.add_argument("--mock", action="store_true"); r.add_argument("--seed", type=int, default=305)
    a = ap.parse_args()
    freeze(a.tasks) if a.cmd == "freeze" else run(a)


if __name__ == "__main__":
    main()
