# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
from cagents.chunking import WhitespaceTokenizer, chunk_records, corpus_hash
from cagents.conditions import TraceLogger, run_condition
from cagents.llm import MockClient
from cagents.retrieval import Index
from conftest import BowEmbedder

TASK = {"task_id": "T-TEST", "grade": 3, "subject": "maths", "outcome_id": "MA-3.1.1.1", "topic": "place value"}
MSG = ("I could not find verified Grade 3 Maths evidence for this outcome in the selected documents. "
       "Please add the relevant curriculum source or choose a supported outcome.")


def test_no_outcome_id_refused_without_similarity(index):
    b = index.retrieve("place value thousands", "maths", 3)
    assert b.status == "insufficient_evidence" and "no outcome ID" in b.reason


def test_similarity_floor_still_applies_when_outcome_not_required(index):
    b = index.retrieve("Shakespeare sonnets iambic pentameter", "maths", 3, threshold=0.99, require_outcome=False)
    assert b.status == "insufficient_evidence" and "below threshold" in b.reason


def test_removed_outcome_fails_inventory_gate(records):
    # TEST 001 style: remove one outcome from a corpus copy, rebuild, request it.
    kept = [r for r in records if r["outcome_id"] != "MA-3.1.1.1"]
    chunks = chunk_records(kept, WhitespaceTokenizer(), size=12, overlap=3)
    idx = Index(BowEmbedder(), path=None, collection="removed")
    idx.build(chunks, corpus_hash(chunks))
    assert "MA-3.1.1.1" not in idx.inventory()[("maths", 3)]
    b = idx.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1")
    assert b.status == "insufficient_evidence" and b.displayed_message == MSG


def test_conflicting_grade_asks_for_consistent_request(index):
    b = index.retrieve("equivalent fractions", "maths", 3, outcome_id="MA-4.5.1.1")
    assert b.status == "conflicting_request" and b.chunks == [] and "not changed" in b.displayed_message


def test_conflicting_subject_detected(index):
    b = index.retrieve("place value", "science", 3, outcome_id="MA-3.1.1.1")
    assert b.status == "conflicting_request"


def test_condition_b_never_calls_model_after_gate_failure(index, tmp_path):
    b = index.retrieve("x", "maths", 3, outcome_id="MA-3.9.9.9")
    client = MockClient([])
    r = run_condition(TASK, "B", client, TraceLogger(tmp_path / "t.jsonl"), bundle=b)
    assert r["status"] == "insufficient_evidence" and r["generation_called"] is False
    assert client.calls == [] and r["output"] is None and r["displayed_message"].startswith("I could not find")
