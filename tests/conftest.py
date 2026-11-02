# AI-written (GenAI assistant), reviewed by Sanjay: see AI_USE.md
import hashlib, json, math, re
import pytest
from cagents.chunking import Chunk, WhitespaceTokenizer, chunk_records, corpus_hash
from cagents.retrieval import Index


class BowEmbedder:
    """Deterministic bag-of-words hashing embedder so retrieval tests run without bge-m3."""
    name = "test-bow"
    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 64
            for w in re.findall(r"[a-z]+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


RECORDS = [
    {"subject": "maths", "grades": [3], "domain": "Numbers", "outcome_id": "MA-3.1.1.1", "text": "read and write place value of whole numbers through thousands"},
    {"subject": "maths", "grades": [3], "domain": "Numbers", "outcome_id": "MA-3.1.2.1", "text": "use place value to compare numbers"},
    {"subject": "maths", "grades": [4], "domain": "Fractions", "outcome_id": "MA-4.5.1.1", "text": "find equivalent fractions using models"},
    {"subject": "science", "grades": [1, 2, 3, 4], "domain": "Earth", "outcome_id": "SC-C1-EARTH", "text": "water cycle evaporation condensation precipitation earth systems"},
    {"subject": "science", "grades": [1, 2, 3, 4], "domain": "Life", "outcome_id": "SC-C1-LIFE", "text": "plants animals life cycles growth living nonliving"},
]
for i, r in enumerate(RECORDS):
    r.update(source_file="moe_test.pdf", file_sha256="abc", doc_id="moe_test", record_no=i)


@pytest.fixture
def records():
    return [dict(r) for r in RECORDS]


@pytest.fixture
def index(records):
    chunks = chunk_records(records, WhitespaceTokenizer(), size=12, overlap=3)
    idx = Index(BowEmbedder(), path=None, collection=f"t{id(records)}")
    idx.build(chunks, corpus_hash(chunks))
    return idx


def lesson(grade=3, subject="maths", cites=("moe-ma-g3-000",), status="ok"):
    if status != "ok":
        return json.dumps({"status": status, "grade": grade, "subject": subject, "reason": "not covered"})
    c = list(cites)
    return json.dumps({"status": "ok", "grade": grade, "subject": subject, "outcome_id": "MA-3.1.1.1", "title": "Place value",
                       "objectives": [{"text": "Read numbers to thousands", "citations": c}],
                       "activities": [{"step": 1, "description": "Base-ten blocks warm-up", "minutes": 10, "citations": c}],
                       "differentiation": {"support": "place value chart", "extension": "five-digit numbers"},
                       "assessment": [{"text": "Exit ticket: write 3 numbers", "citations": c}], "feedback": "Praise strategy use."})
