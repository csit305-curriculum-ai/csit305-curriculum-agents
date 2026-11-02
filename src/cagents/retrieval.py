"""Embedding, Chroma index, top-k retrieval, coverage gate and frozen evidence bundle (Doc 3 T4, ARCH 002)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import chromadb

from .chunking import Chunk

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "index" / "chroma"
COLLECTION = "uae_moe_cycle1"
TOP_K = 5
# Cosine-similarity floor for the coverage gate. Chosen from the calibration in DESIGN_DECISIONS.md DEC 008.
SIM_THRESHOLD = 0.50
EMBED_MODEL = "BAAI/bge-m3"


class Embedder(Protocol):
    name: str
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class BGEM3Embedder:
    """bge-m3 dense embeddings via sentence-transformers on CPU, L2-normalised."""

    def __init__(self, model: str = EMBED_MODEL, max_seq_length: int = 512) -> None:
        from sentence_transformers import SentenceTransformer
        self.name = model
        self.model = SentenceTransformer(model, device="cpu")
        self.model.max_seq_length = max_seq_length
        self.tokenizer = self.model.tokenizer

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, batch_size=8, normalize_embeddings=True, show_progress_bar=False).tolist()


class HFTokenizerAdapter:
    """Adapts the embedding model's tokenizer to the chunking Tokenizer protocol (no special tokens)."""

    def __init__(self, tok) -> None:
        self.tok = tok

    def encode(self, text: str) -> list[int]:
        return self.tok(text, add_special_tokens=False)["input_ids"]

    def decode(self, ids: list[int]) -> str:
        return self.tok.decode(ids, skip_special_tokens=True)


@dataclass
class EvidenceBundle:
    query: str
    subject: str
    grade: int
    outcome_id: str | None
    status: str  # "ok" | "insufficient_evidence"
    reason: str
    chunks: list[dict] = field(default_factory=list)  # chunk_id, text, score, outcome_ids, source_file
    corpus_hash: str = ""
    embed_model: str = ""
    threshold: float = SIM_THRESHOLD
    bundle_hash: str = ""

    @property
    def chunk_ids(self) -> list[str]:
        return [c["chunk_id"] for c in self.chunks]

    def compute_hash(self) -> str:
        payload = json.dumps({"q": self.query, "s": self.subject, "g": self.grade, "o": self.outcome_id,
                              "status": self.status, "chunks": [(c["chunk_id"], c["text"]) for c in self.chunks],
                              "corpus": self.corpus_hash}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def freeze(self) -> "EvidenceBundle":
        self.bundle_hash = self.compute_hash()
        return self

    def verify(self) -> None:
        """Doc 3: a changed packet must stop the run."""
        if self.bundle_hash != self.compute_hash():
            raise RuntimeError("Evidence bundle hash mismatch: packet changed after freezing; run stopped.")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class Index:
    def __init__(self, embedder: Embedder, path: Path | None = INDEX_DIR, collection: str = COLLECTION) -> None:
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(path)) if path else chromadb.EphemeralClient()
        self.col = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})

    def build(self, chunks: list[Chunk], corpus_hash: str) -> None:
        existing = self.col.get()["ids"]
        if existing:
            self.col.delete(ids=existing)
        vecs = self.embedder.embed([c.text for c in chunks])
        metas = [dict(c.metadata(), corpus_hash=corpus_hash) for c in chunks]
        self.col.add(ids=[c.chunk_id for c in chunks], documents=[c.text for c in chunks], embeddings=vecs, metadatas=metas)

    def corpus_hash(self) -> str:
        got = self.col.get(limit=1, include=["metadatas"])
        return got["metadatas"][0]["corpus_hash"] if got["metadatas"] else ""

    def retrieve(self, query: str, subject: str, grade: int, outcome_id: str | None = None,
                 k: int = TOP_K, threshold: float = SIM_THRESHOLD, exclude_outcomes: set[str] | None = None) -> EvidenceBundle:
        b = EvidenceBundle(query=query, subject=subject, grade=grade, outcome_id=outcome_id, status="ok", reason="",
                           corpus_hash=self.corpus_hash(), embed_model=self.embedder.name, threshold=threshold)
        if not 1 <= grade <= 4:
            b.status, b.reason = "insufficient_evidence", f"grade {grade} outside corpus scope (Cycle 1, Grades 1-4)"
            return b.freeze()
        where = {"$and": [{"subject": subject}, {f"g{grade}": True}]}
        res = self.col.query(query_embeddings=self.embedder.embed([query]), n_results=k, where=where,
                             include=["documents", "metadatas", "distances"])
        hits = []
        for cid, doc, md, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            oids = [o for o in md["outcome_ids"].split(",") if o]
            if exclude_outcomes and set(oids) & exclude_outcomes:
                continue  # used by the missing-outcome test (TEST 001) to simulate a removed outcome
            hits.append({"chunk_id": cid, "text": doc, "score": round(1.0 - dist, 4), "outcome_ids": oids,
                         "source_file": md["source_file"]})
        if not hits:
            b.status, b.reason = "insufficient_evidence", "no chunks for this grade/subject filter"
        elif hits[0]["score"] < threshold:
            b.status, b.reason = "insufficient_evidence", f"best similarity {hits[0]['score']} below threshold {threshold}"
        elif outcome_id and not any(outcome_id in h["outcome_ids"] for h in hits):
            b.status, b.reason = "insufficient_evidence", f"requested outcome {outcome_id} not in retrieved evidence"
        if b.status == "ok":
            b.chunks = hits
        return b.freeze()
