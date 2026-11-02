# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
from cagents.conditions import TraceLogger, run_condition
from cagents.llm import MockClient

TASK = {"task_id": "T-TEST", "grade": 3, "subject": "maths", "outcome_id": "MA-3.1.1.1", "topic": "place value"}


def test_below_threshold_returns_insufficient(index):
    b = index.retrieve("Shakespeare sonnets iambic pentameter", "maths", 3, threshold=0.99)
    assert b.status == "insufficient_evidence" and "below threshold" in b.reason and b.chunks == []


def test_missing_outcome_is_not_covered(index):
    # TEST 001 style: remove one outcome from the evidence and request it
    b = index.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1", threshold=0.0,
                       exclude_outcomes={"MA-3.1.1.1"})
    assert b.status == "insufficient_evidence"


def test_condition_b_never_calls_model_after_gate_failure(index, tmp_path):
    b = index.retrieve("x", "maths", 3, outcome_id="MA-9.9.9.9", threshold=0.0)
    client = MockClient([])
    r = run_condition(TASK, "B", client, TraceLogger(tmp_path / "t.jsonl"), bundle=b)
    assert r["status"] == "insufficient_evidence" and r["generation_called"] is False
    assert client.calls == [] and r["output"] is None
