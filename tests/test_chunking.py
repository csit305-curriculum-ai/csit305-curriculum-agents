# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
import pytest
from cagents.chunking import WhitespaceTokenizer, chunk_records, corpus_hash, window


def test_window_sizes_and_overlap():
    spans = window(list(range(1000)), 400, 80)
    assert spans[0] == (0, 400) and spans[1] == (320, 720) and spans[-1][1] == 1000
    for (a1, b1), (a2, _) in zip(spans, spans[1:]):
        assert b1 - a2 == 80  # consecutive windows overlap by exactly 80 tokens


def test_window_short_and_empty():
    assert window(list(range(50)), 400, 80) == [(0, 50)]
    assert window([], 400, 80) == []
    with pytest.raises(ValueError):
        window([1, 2, 3], 80, 80)


def test_chunks_never_mix_grade_or_subject(records):
    chunks = chunk_records(records, WhitespaceTokenizer(), size=12, overlap=3)
    for c in chunks:
        assert c.n_tokens <= 12
        if c.subject == "maths":
            assert len(c.grades) == 1
    assert {c.subject for c in chunks} == {"maths", "science"}


def test_chunk_ids_unique_and_outcomes_traced(records):
    chunks = chunk_records(records, WhitespaceTokenizer(), size=40, overlap=8)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    g3 = [c for c in chunks if c.grades == [3]][0]
    assert "MA-3.1.1.1" in g3.outcome_ids


def test_corpus_hash_changes_with_text(records):
    a = chunk_records(records, WhitespaceTokenizer(), 40, 8)
    records[0]["text"] += " changed"
    b = chunk_records(records, WhitespaceTokenizer(), 40, 8)
    assert corpus_hash(a) != corpus_hash(b)
