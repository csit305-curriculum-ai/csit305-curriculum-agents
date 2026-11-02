# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
# Integration test on the real bge-m3 + Chroma index. Skipped if the index has not been built.
import pytest
from cagents.retrieval import INDEX_DIR

pytestmark = pytest.mark.skipif(not INDEX_DIR.exists(), reason="run python -m cagents.build_index first")


@pytest.fixture(scope="module")
def real():
    from cagents.retrieval import BGEM3Embedder, Index
    return Index(BGEM3Embedder())


def test_grade3_place_value_outcome_retrieved(real):
    b = real.retrieve("read, write and identify place value of whole numbers through thousands", "maths", 3,
                      outcome_id="MA-3.1.1.1")
    assert b.status == "ok", b.reason
    assert all("-g3-" in c for c in b.chunk_ids)


def test_off_curriculum_query_refused(real):
    b = real.retrieve("the causes of the French Revolution", "maths", 3)
    assert b.status == "insufficient_evidence"


def test_timss_not_indexed_so_science_refused(real):
    b = real.retrieve("water cycle", "science", 4)
    assert b.status == "insufficient_evidence" and "no indexed evidence" in b.reason  # DEC 012


def test_outcome_chunk_carries_pages(real):
    b = real.retrieve("adding multi-digit whole numbers", "maths", 4, outcome_id="MA-4.2.5.1")
    assert b.status == "ok" and "MA-4.2.5.1" in b.chunks[0]["outcome_ids"] and b.chunks[0]["pages"]
