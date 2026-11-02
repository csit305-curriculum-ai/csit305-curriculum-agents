# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
import pytest


def test_topk_respects_filters(index):
    b = index.retrieve("place value thousands", "maths", 3, threshold=0.0)
    assert b.status == "ok" and 1 <= len(b.chunks) <= 5
    assert all("-g3-" in cid for cid in b.chunk_ids)
    scores = [c["score"] for c in b.chunks]
    assert scores == sorted(scores, reverse=True)


def test_science_cycle1_visible_for_grade4(index):
    b = index.retrieve("water cycle evaporation", "science", 4, threshold=0.0)
    assert b.status == "ok" and b.chunk_ids


def test_bundle_hash_frozen_and_tamper_detected(index):
    b = index.retrieve("place value", "maths", 3, threshold=0.0)
    h = b.bundle_hash
    assert len(h) == 64
    b2 = index.retrieve("place value", "maths", 3, threshold=0.0)
    assert b2.bundle_hash == h  # deterministic for the same query and corpus
    b.chunks[0]["text"] += " tampered"
    with pytest.raises(RuntimeError, match="hash mismatch"):
        b.verify()


def test_out_of_scope_grade_rejected(index):
    b = index.retrieve("place value", "maths", 6)
    assert b.status == "insufficient_evidence" and b.chunks == []
