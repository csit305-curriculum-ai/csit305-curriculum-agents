# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
import json
import pytest
from conftest import pack
from cagents.checker_inputs import checker_rows
from cagents.conditions import TraceLogger, run_condition
from cagents.llm import LLMTimeout, LLMTransientError, MockClient
from cagents.schema import OutputError, parse_and_check, parse_section, word_count

TASK = {"task_id": "T-TEST", "grade": 3, "subject": "maths", "outcome_id": "MA-3.1.1.1", "topic": "place value"}


def test_valid_b_output_passes():
    out = parse_and_check(pack(), "B", 3, "maths", ["moe-ma-g3-000"])
    assert out.status == "ok" and out.assessment.questions[0].answer_key == "400"


@pytest.mark.parametrize("raw,allowed,cond,msg", [
    ("{not json", [], "A", "malformed JSON"),
    (pack(cites=("moe-ma-g3-999",)), ["moe-ma-g3-000"], "B", "invalid citation"),
    (pack(cites=()), ["moe-ma-g3-000"], "B", "must cite"),
    (pack(), [], "A", "must not cite"),
    (pack(grade=4), ["moe-ma-g3-000"], "B", "grade/subject changed"),
    (pack(obj_ref="O9"), ["moe-ma-g3-000"], "B", "objective_ids not defined"),
    (json.dumps({"status": "ok", "grade": 3, "subject": "maths"}), [], "A", "four sections"),
])
def test_invalid_outputs_rejected(raw, allowed, cond, msg):
    with pytest.raises(OutputError, match=msg):
        parse_and_check(raw, cond, 3, "maths", allowed)


def test_missing_answer_key_rejected():
    d = pack(as_dict=True)
    del d["assessment"]["questions"][0]["answer_key"]
    with pytest.raises(OutputError, match="answer_key"):
        parse_and_check(json.dumps(d), "B", 3, "maths", ["moe-ma-g3-000"])


def test_section_validation_for_condition_c():
    d = pack(as_dict=True)
    sec = parse_section(json.dumps({"assessment": d["assessment"]}), "assessment", "C", ["moe-ma-g3-000"], {"O1"})
    assert sec.questions[0].question_id == "Q1"
    with pytest.raises(OutputError, match="invalid citation"):
        parse_section(json.dumps({"assessment": d["assessment"]}), "assessment", "C", ["other"], {"O1"})
    with pytest.raises(OutputError, match="objective_ids"):
        parse_section(json.dumps(d["assessment"]), "assessment", "C", ["moe-ma-g3-000"], {"O2"})


def test_retry_once_then_success_counts_both(index, tmp_path):
    b = index.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1")
    client = MockClient(["{bad", pack(cites=(b.chunk_ids[0],))])
    log = tmp_path / "t.jsonl"
    r = run_condition(TASK, "B", client, TraceLogger(log), bundle=b, job_id="J1")
    assert r["status"] == "ok" and r["completion"] == 1 and r["attempts"] == 2 and len(client.calls) == 2
    assert "rejected" in client.calls[1]["messages"][-1]["content"]
    events = [json.loads(l) for l in log.read_text().splitlines()]
    assert [e["event"] for e in events] == ["attempt", "attempt", "result"]
    e = events[0]
    assert e["chunk_ids"] == b.chunk_ids and e["job_id"] == "J1" and e["node"] == "single"
    assert e["requested_model"] == "deepseek-flash" and "returned_model" in e and "usd_per_1M" in e["pricing_snapshot"]
    assert r["total_latency_s"] >= r["retrieval_latency_s"] and r["word_count"] > 0


def test_retry_only_once_then_invalid_keeps_candidate(tmp_path):
    bad = pack(cites=("moe-ma-g3-000",))  # A must not cite
    client = MockClient([bad, bad])
    r = run_condition(TASK, "A", client, TraceLogger(tmp_path / "t.jsonl"))
    assert r["status"] == "invalid_output" and r["completion"] == 0 and r["attempts"] == 2
    assert r["output_candidate"]["planning"]["objectives"][0]["citations"] == ["moe-ma-g3-000"]


def test_timeout_one_bounded_retry_with_delay_then_incomplete(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("cagents.conditions.time.sleep", lambda s: slept.append(s))
    client = MockClient([LLMTimeout("t1"), LLMTransientError("503")])
    log = tmp_path / "t.jsonl"
    r = run_condition(TASK, "A", client, TraceLogger(log))
    assert r["status"] == "incomplete" and r["attempts"] == 2 and slept == [5.0]
    assert [json.loads(l)["event"] for l in log.read_text().splitlines()] == ["api_error", "api_error", "result"]


def test_timeout_then_success(tmp_path, monkeypatch):
    monkeypatch.setattr("cagents.conditions.time.sleep", lambda s: None)
    r = run_condition(TASK, "A", MockClient([LLMTimeout("t1"), pack(cites=())]), TraceLogger(tmp_path / "t.jsonl"))
    assert r["status"] == "ok" and r["attempts"] == 2


def test_condition_a_has_no_evidence_in_prompt(tmp_path):
    client = MockClient([pack(cites=())])
    r = run_condition(TASK, "A", client, TraceLogger(tmp_path / "t.jsonl"))
    assert r["status"] == "ok"
    assert "<passage" not in json.dumps(client.calls[0]["messages"])
    assert client.calls[0]["max_tokens"] == 2400


def test_checker_rows_include_cited_passages_and_invalid_ids(index):
    b = index.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1")
    d = pack(cites=(b.chunk_ids[0], "fake-id"), as_dict=True)
    rows = checker_rows("R1", d, b)
    assert rows[0]["section"] == "planning" and rows[0]["passages"][0]["chunk_id"] == b.chunk_ids[0]
    assert rows[0]["invalid_ids"] == ["fake-id"]  # fabricated ID: counted as cited, unsupported
    assert any(r["missing_citation"] for r in rows) and word_count(d) > 0
