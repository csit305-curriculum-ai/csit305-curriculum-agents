"""Condition C tests. AI-written (Grok Bot) at Sanjay's request, 2 Nov 2026; pending Manzi review (AI_USE.md).
All use MockClient / ScriptedSpecialistClient: no API calls."""
import json

import pytest

from cagents.condition_c import MAX_TOKENS_C_NODE, NODES, assemble, node_messages, run_condition_c
from cagents.conditions import TraceLogger
from cagents.llm import LLMTimeout, MockClient
from cagents.retrieval import PacketMismatch, assert_reproduces
from cagents.schema import TeachingPack
from cagents.scripted import ScriptedSpecialistClient, scripted_section

TASK = {"task_id": "T-C", "grade": 3, "subject": "maths", "outcome_id": "MA-3.1.1.1", "topic": "place value"}


@pytest.fixture
def bundle(index):
    b = index.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1")
    assert b.status == "ok"
    return b


def secs(ids):
    return {n: json.dumps(scripted_section(n.upper(), ids, "place value")) for n in NODES}


def trace(p):
    return [json.loads(l) for l in p.read_text().splitlines()]


def run(bundle, tmp_path, outputs=None, **kw):
    s = secs(bundle.chunk_ids)
    client = MockClient(outputs if outputs is not None else [s[n] for n in NODES])
    r = run_condition_c(TASK, client, TraceLogger(tmp_path / "t.jsonl"), bundle, retry_delay_s=0, **kw)
    return r, client


def test_nodes_run_in_fixed_order_planning_differentiation_assessment_feedback(bundle, tmp_path):
    r, client = run(bundle, tmp_path)
    seen = [c["messages"][0]["content"].split("You are the ")[1].split(" ")[0].lower() for c in client.calls]
    assert seen == list(NODES) and [n["node"] for n in r["nodes"]] == list(NODES)
    assert r["status"] == "ok" and r["job_status"] == "ok"


def test_every_node_receives_identical_frozen_packet(bundle, tmp_path):
    _, client = run(bundle, tmp_path)
    blocks = [c["messages"][1]["content"].split("\n\nTask ")[0] for c in client.calls]
    assert len(set(blocks)) == 1 and bundle.bundle_hash[:12] in blocks[0]
    assert all(cid in blocks[0] for cid in bundle.chunk_ids)


def test_downstream_nodes_receive_only_their_upstream_drafts(bundle, tmp_path):
    _, client = run(bundle, tmp_path)
    u = [c["messages"][1]["content"] for c in client.calls]
    assert "EARLIER DRAFT" not in u[0]
    assert "EARLIER DRAFT (planning" in u[1] and "EARLIER DRAFT (assessment" not in u[1]
    assert "EARLIER DRAFT (planning" in u[3] and "EARLIER DRAFT (assessment" in u[3]


def test_timed_c_request_must_reproduce_frozen_packet(index, bundle):
    other = index.retrieve("compare numbers place value", "maths", 3, outcome_id="MA-3.1.2.1")
    assert_reproduces(bundle, index.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1"))
    with pytest.raises(PacketMismatch):
        assert_reproduces(bundle, other)


def test_tampered_packet_stops_before_any_call(bundle, tmp_path):
    bundle.chunks[0]["text"] += " tampered"
    with pytest.raises(RuntimeError):
        run(bundle, tmp_path)


def test_node_citations_restricted_to_packet_chunk_ids(bundle, tmp_path):
    bad = json.dumps(scripted_section("PLANNING", ["moe-ma-g9-999"], "x"))
    r, client = run(bundle, tmp_path, outputs=[bad, bad])
    assert r["job_status"] == "incomplete" and r["failed_node"] == "planning"
    assert "invalid citation IDs" in r["reason"] and len(client.calls) == 2


def test_invalid_node_output_regenerates_once_and_counts_both_attempts(bundle, tmp_path):
    s = secs(bundle.chunk_ids)
    r, client = run(bundle, tmp_path, outputs=[s["planning"], "{not json", s["differentiation"], s["assessment"], s["feedback"]])
    assert r["status"] == "ok" and r["nodes"][1]["attempts"] == 2 and r["attempts"] == 5 and r["model_calls"] == 5
    assert "rejected" in client.calls[2]["messages"][-1]["content"]


def test_timeout_gets_one_bounded_retry_then_incomplete(bundle, tmp_path):
    r, _ = run(bundle, tmp_path, outputs=[LLMTimeout("t"), LLMTimeout("t")])
    assert r["job_status"] == "incomplete" and r["failed_node"] == "planning" and r["api_failures"] == 2


def test_failed_node_marks_job_incomplete_and_never_substitutes_b(bundle, tmp_path):
    s = secs(bundle.chunk_ids)
    r, client = run(bundle, tmp_path, outputs=[s["planning"], s["differentiation"], "{}", "{}"])
    assert r["job_status"] == "incomplete" and r["failed_node"] == "assessment" and r["output"] is None
    assert r["condition"] == "C" and len(client.calls) == 4  # feedback never called
    assert set(r["output_candidate"]) == {"planning", "differentiation"}


def test_assembly_is_python_only_no_fifth_model_call(bundle, tmp_path):
    r, client = run(bundle, tmp_path)
    assert len(client.calls) == 4 and r["model_calls"] == 4
    TeachingPack.model_validate(r["output"])
    assert r["output"]["title"] == TASK["topic"] and r["output"]["outcome_id"] == "MA-3.1.1.1"


def test_cross_section_links_reference_existing_objective_and_question_ids(bundle, tmp_path):
    s = secs(bundle.chunk_ids)
    d = scripted_section("DIFFERENTIATION", bundle.chunk_ids, "x")
    d["differentiation"]["support"][0]["objective_ids"] = ["O9"]
    r, _ = run(bundle, tmp_path, outputs=[s["planning"], json.dumps(d), json.dumps(d)])
    assert r["failed_node"] == "differentiation" and "O9" in r["reason"]
    ok, _ = run(bundle, tmp_path)
    objs = {o["objective_id"] for o in ok["output"]["planning"]["objectives"]}
    assert all(set(q["objective_ids"]) <= objs for q in ok["output"]["assessment"]["questions"])


def test_planning_lesson_sequence_must_use_own_objectives(bundle, tmp_path):
    p = scripted_section("PLANNING", bundle.chunk_ids, "x")
    p["planning"]["lesson_sequence"][0]["objective_ids"] = ["O7"]
    r, _ = run(bundle, tmp_path, outputs=[json.dumps(p)] * 2)
    assert r["failed_node"] == "planning"


def test_per_node_and_job_log_fields_present_and_costs_sum(bundle, tmp_path):
    r, _ = run(bundle, tmp_path)
    recs = trace(tmp_path / "t.jsonl")
    att = [e for e in recs if e["event"] == "attempt"]
    nodes = [e for e in recs if e["event"] == "node_result"]
    job = [e for e in recs if e["event"] == "result"][0]
    for e in att:
        for k in ("run_id", "job_id", "node", "task_id", "condition", "repeat", "bundle_hash", "chunk_ids", "attempt",
                  "prompt_tokens", "completion_tokens", "cached_tokens", "latency_s", "finish_reason", "cost_usd", "valid"):
            assert k in e, k
    assert [e["node"] for e in nodes] == list(NODES)
    assert job["prompt_tokens"] == sum(e["prompt_tokens"] for e in att)
    assert job["completion_tokens"] == sum(e["completion_tokens"] for e in att)
    assert job["cost_usd"] == pytest.approx(sum(e["cost_usd"] for e in nodes), abs=1e-6)


def test_each_specialist_capped_at_800_output_tokens(bundle, tmp_path):
    _, client = run(bundle, tmp_path)
    assert MAX_TOKENS_C_NODE == 800 and all(c["max_tokens"] == 800 for c in client.calls)


def test_gate_failure_refuses_without_any_model_call(index, tmp_path):
    b = index.retrieve("x", "maths", 3, outcome_id="MA-3.9.9.9")
    client = MockClient([])
    r = run_condition_c(TASK, client, TraceLogger(tmp_path / "t.jsonl"), b)
    assert r["status"] == "insufficient_evidence" and r["generation_called"] is False and client.calls == []
    assert r["displayed_message"].startswith("I could not find") and r["model_calls"] == 0


def test_scripted_client_runs_end_to_end(bundle, tmp_path):
    c = ScriptedSpecialistClient()
    r = run_condition_c(TASK, c, TraceLogger(tmp_path / "t.jsonl"), bundle)
    assert r["status"] == "ok" and len(c.calls) == 4 and r["word_count"] > 0
