# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
import pytest
from cagents.retrieval import PacketMismatch, assert_reproduces


def test_outcome_first_packet_respects_filters(index):
    b = index.retrieve("place value thousands", "maths", 3, outcome_id="MA-3.1.1.1")
    assert b.status == "ok" and 1 <= len(b.chunks) <= 5
    assert all("-g3-" in cid for cid in b.chunk_ids)
    assert "MA-3.1.1.1" in b.chunks[0]["outcome_ids"]  # outcome chunk first (DEC 013)
    assert b.chunks[0]["pages"] and b.chunks[0]["source_file"] == "moe_test.pdf"


def test_science_cycle1_visible_for_grade4(index):
    b = index.retrieve("water cycle evaporation", "science", 4, outcome_id="SC-C1-EARTH")
    assert b.status == "ok" and b.chunk_ids


def test_bundle_hash_frozen_and_tamper_detected(index):
    b = index.retrieve("place value", "maths", 3, outcome_id="MA-3.1.1.1")
    assert len(b.bundle_hash) == 64
    assert index.retrieve("place value", "maths", 3, outcome_id="MA-3.1.1.1").bundle_hash == b.bundle_hash
    b.chunks[0]["text"] += " tampered"
    with pytest.raises(RuntimeError, match="hash mismatch"):
        b.verify()


def test_live_retrieval_must_reproduce_frozen_packet(index):
    frozen = index.retrieve("place value", "maths", 3, outcome_id="MA-3.1.1.1")
    assert_reproduces(frozen, index.retrieve("place value", "maths", 3, outcome_id="MA-3.1.1.1"))
    with pytest.raises(PacketMismatch):
        assert_reproduces(frozen, index.retrieve("compare numbers", "maths", 3, outcome_id="MA-3.1.2.1"))


def test_out_of_scope_grade_rejected(index):
    b = index.retrieve("place value", "maths", 6)
    assert b.status == "insufficient_evidence" and b.chunks == []
