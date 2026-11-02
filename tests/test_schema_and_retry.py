# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
import json
import pytest
from conftest import lesson
from cagents.conditions import TraceLogger, run_condition
from cagents.llm import LLMTimeout, MockClient
from cagents.schema import OutputError, parse_and_check

TASK = {"task_id": "T-TEST", "grade": 3, "subject": "maths", "outcome_id": "MA-3.1.1.1", "topic": "place value"}


def test_valid_b_output_passes():
    out = parse_and_check(lesson(), "B", 3, "maths", ["moe-ma-g3-000"])
    assert out.status == "ok"


@pytest.mark.parametrize("raw,allowed,cond,msg", [
    ("{not json", [], "A", "malformed JSON"),
    (lesson(cites=("moe-ma-g3-999",)), ["moe-ma-g3-000"], "B", "invalid citation"),
    (lesson(cites=()), ["moe-ma-g3-000"], "B", "must cite"),
    (lesson(), [], "A", "must not cite"),
    (lesson(grade=4), ["moe-ma-g3-000"], "B", "mismatch"),
    (json.dumps({"status": "ok", "grade": 3, "subject": "maths"}), [], "A", "schema"),
])
def test_invalid_outputs_rejected(raw, allowed, cond, msg):
    with pytest.raises(OutputError, match=msg):
        parse_and_check(raw, cond, 3, "maths", allowed)


def test_retry_once_then_success_counts_both(index, tmp_path):
    b = index.retrieve("place value thousands", "maths", 3, threshold=0.0)
    good = lesson(cites=(b.chunk_ids[0],))
    client = MockClient(["{bad", good])
    log = tmp_path / "t.jsonl"
    r = run_condition(TASK, "B", client, TraceLogger(log), bundle=b)
    assert r["status"] == "ok" and r["attempts"] == 2 and len(client.calls) == 2
    assert "rejected" in client.calls[1]["messages"][-1]["content"]
    events = [json.loads(l) for l in log.read_text().splitlines()]
    assert [e["event"] for e in events] == ["attempt", "attempt", "result"]
    assert events[0]["chunk_ids"] == b.chunk_ids and "prompt_tokens" in events[0] and "latency_s" in events[0]


def test_retry_only_once_then_invalid(tmp_path):
    client = MockClient(["{bad", "{still bad"])
    r = run_condition(TASK, "A", client, TraceLogger(tmp_path / "t.jsonl"))
    assert r["status"] == "invalid_output" and r["attempts"] == 2 and client.outputs == []


def test_timeout_one_bounded_retry_then_incomplete(tmp_path):
    client = MockClient([LLMTimeout("t1"), LLMTimeout("t2")])
    r = run_condition(TASK, "A", client, TraceLogger(tmp_path / "t.jsonl"))
    assert r["status"] == "incomplete" and r["attempts"] == 2


def test_condition_a_has_no_evidence_in_prompt(tmp_path):
    client = MockClient([lesson(cites=())])
    r = run_condition(TASK, "A", client, TraceLogger(tmp_path / "t.jsonl"))
    assert r["status"] == "ok"
    assert "<chunk" not in json.dumps(client.calls[0]["messages"])
    assert client.calls[0]["max_tokens"] == 2400
