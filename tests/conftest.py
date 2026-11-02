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
    r.update(source_file="moe_test.pdf", file_sha256="abc", doc_id="moe_test", record_no=i, page=10 + i, role="evidence")


@pytest.fixture
def records():
    return [dict(r) for r in RECORDS]


@pytest.fixture
def index(records):
    chunks = chunk_records(records, WhitespaceTokenizer(), size=12, overlap=3)
    idx = Index(BowEmbedder(), path=None, collection=f"t{id(records)}")
    idx.build(chunks, corpus_hash(chunks))
    return idx


def pack(grade=3, subject="maths", cites=("moe-ma-g3-000",), status="ok", obj_ref="O1", as_dict=False):
    """A valid four-section teaching pack (Doc 3: objectives+sequence, support+extension, questions+keys, feedback)."""
    if status != "ok":
        d = {"status": status, "grade": grade, "subject": subject, "reason": "not covered"}
    else:
        c = list(cites)
        d = {"status": "ok", "grade": grade, "subject": subject, "outcome_id": "MA-3.1.1.1", "title": "Place value",
             "planning": {"objectives": [{"objective_id": "O1", "text": "Read numbers to thousands", "citations": c}],
                          "lesson_sequence": [{"step": 1, "description": "Base-ten blocks warm-up", "minutes": 10,
                                               "objective_ids": [obj_ref], "citations": c}]},
             "differentiation": {"support": [{"description": "Use a place value chart", "objective_ids": ["O1"], "citations": c}],
                                 "extension": [{"description": "Five-digit numbers", "objective_ids": ["O1"], "citations": []}]},
             "assessment": {"questions": [{"question_id": "Q1", "question": "What is the value of 4 in 3,482?",
                                           "answer_key": "400", "objective_ids": ["O1"], "citations": c}]},
             "feedback": {"templates": [{"answer_pattern": "Answers 4", "feedback": "Look at which column the 4 is in.",
                                         "objective_ids": ["O1"], "citations": []}]},
             "reason": ""}
    return d if as_dict else json.dumps(d)


lesson = pack  # backwards-compatible name
