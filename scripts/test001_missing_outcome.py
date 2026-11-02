"""TEST 001 (Doc 3 failure protocol). Default target is the Grade 4 Science outcome SC-4.4.3.2.2 (DEC 016), as Doc 3
specifies; pass MA-4.2.5.1 to repeat the earlier provisional Maths variant (DEC 015). Condition B only (C not built yet). No API call is possible: a MockClient with no
scripted outputs raises if generation is ever called.
Usage: cd src && ../.venv/bin/python ../scripts/test001_missing_outcome.py [OUTCOME_ID]"""
import csv, hashlib, json, sys, time
from pathlib import Path

from cagents import corpus
from cagents.chunking import chunk_records, corpus_hash
from cagents.conditions import TraceLogger, run_condition
from cagents.llm import MockClient
from cagents.retrieval import ROOT, BGEM3Embedder, HFTokenizerAdapter, Index

TARGET = sys.argv[1] if len(sys.argv) > 1 else "SC-4.4.3.2.2"
SCI = TARGET.startswith("SC-")
SUBJECT = "science" if SCI else "maths"
TASK = {"task_id": "TEST001", "grade": 4, "subject": SUBJECT, "outcome_id": TARGET,
        "topic": "Designing a simple working electrical circuit" if SCI else "Adding multi-digit whole numbers"}
EXPECTED = (f"I could not find verified Grade 4 {'Science' if SCI else 'Maths'} evidence for this outcome in the selected "
            "documents. Please add the relevant curriculum source or choose a supported outcome.")
OUT = ROOT / "runs" / ("test001_science" if SCI else "test001")


def h(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    corpus.verify_sources()
    original = corpus.evidence_records(corpus.build())
    modified = [r for r in original if r["outcome_id"] != TARGET]  # the corpus COPY; originals untouched
    removed = len(original) - len(modified)
    emb = BGEM3Embedder()
    chunks = chunk_records(modified, HFTokenizerAdapter(emb.tokenizer))
    check = {"removed_records": removed, "in_modified_records": any(r["outcome_id"] == TARGET for r in modified),
             "in_modified_chunk_text": any(f"[{TARGET}]" in c.text for c in chunks)}
    assert removed >= 1 and not check["in_modified_records"] and not check["in_modified_chunk_text"], check
    idx = Index(emb, path=None, collection="test001")
    idx.build(chunks, corpus_hash(chunks))
    OUT.mkdir(parents=True, exist_ok=True)
    logger, rows = TraceLogger(OUT / "trace.jsonl"), []
    for i in range(1, 11):
        t0 = time.perf_counter()
        b = idx.retrieve(TASK["topic"], SUBJECT, 4, outcome_id=TARGET)
        client = MockClient([])
        r = run_condition(TASK, "B", client, logger, bundle=b, repeat=i)
        ok = (r["status"] == "insufficient_evidence" and not client.calls and r["displayed_message"] == EXPECTED)
        rows.append({"attempt": i, "condition": "B", "request": json.dumps(TASK), "original_records_sha256": h(original),
                     "modified_records_sha256": h(modified), "modified_corpus_hash": idx.corpus_hash(),
                     "retrieved_ids": ";".join(b.chunk_ids), "status": r["status"], "generation_called": bool(client.calls),
                     "displayed_response": r["displayed_message"], "elapsed_s": round(time.perf_counter() - t0, 3),
                     "pass": ok})
    with (OUT / "test001_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (OUT / "removal_check.json").write_text(json.dumps(dict(check, target=TARGET, original_sha256=h(original),
                                                            modified_sha256=h(modified)), indent=1))
    print(f"{sum(r['pass'] for r in rows)}/10 B attempts passed; removal check {check}")


if __name__ == "__main__":
    main()
