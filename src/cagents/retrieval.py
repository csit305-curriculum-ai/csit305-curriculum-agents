"""Embedding, Chroma index, top-k retrieval, coverage gate and frozen evidence bundle (Doc 3 T4, ARCH 002)."""
from __future__ import annotations

import hashlib
import json
import re
import time
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


INSUFFICIENT_MSG = ("I could not find verified Grade {grade} {subject_title} evidence for this outcome in the selected "
                    "documents. Please add the relevant curriculum source or choose a supported outcome.")


def outcome_grade_subject(outcome_id: str) -> tuple[int | None, str | None]:
    """MA-3.1.1.1 -> (3, 'maths'). Unknown formats -> (None, None)."""
    m = re.match(r"^(MA|SC)-(\d+)\.", outcome_id or "")
    if not m:
        return None, None
    return int(m.group(2)), {"MA": "maths", "SC": "science"}[m.group(1)]


@dataclass
class EvidenceBundle:
    """Packet E (Doc 3 Stage 2 / T4): passage text, IDs and metadata in a fixed order, plus a hash."""
    query: str
    subject: str
    grade: int
    outcome_id: str | None
    status: str  # "ok" | "insufficient_evidence" | "conflicting_request"
    reason: str
    chunks: list[dict] = field(default_factory=list)  # chunk_id, text, score, outcome_ids, source_file, file_sha256, pages
    corpus_hash: str = ""
    embed_model: str = ""
    threshold: float = SIM_THRESHOLD
    top_k: int = TOP_K
    displayed_message: str = ""
    retrieval_latency_s: float = 0.0
    bundle_hash: str = ""

    @property
    def chunk_ids(self) -> list[str]:
        return [c["chunk_id"] for c in self.chunks]

    def compute_hash(self) -> str:
        payload = json.dumps({"q": self.query, "s": self.subject, "g": self.grade, "o": self.outcome_id, "status": self.status,
                              "chunks": [(c["chunk_id"], c["text"], c["source_file"], c["pages"]) for c in self.chunks],
                              "corpus": self.corpus_hash, "k": self.top_k, "t": self.threshold, "m": self.embed_model},
                             sort_keys=True, ensure_ascii=False)
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

    @classmethod
    def from_json(cls, s: str) -> "EvidenceBundle":
        return cls(**json.loads(s))


class PacketMismatch(RuntimeError):
    pass


def assert_reproduces(frozen: EvidenceBundle, live: EvidenceBundle) -> None:
    """Doc 3 Stage 2: the timed request repeats retrieval and must reproduce the frozen packet."""
    frozen.verify()
    if live.bundle_hash != frozen.bundle_hash:
        raise PacketMismatch(f"live packet {live.bundle_hash[:12]} != frozen {frozen.bundle_hash[:12]}; run stopped for investigation")


class Index:
    def __init__(self, embedder: Embedder, path: Path | None = INDEX_DIR, collection: str = COLLECTION) -> None:
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(path)) if path else chromadb.EphemeralClient()
        self.col = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        self._inventory: dict | None = None

    def build(self, chunks: list[Chunk], corpus_hash: str) -> None:
        existing = self.col.get()["ids"]
        if existing:
            self.col.delete(ids=existing)
        vecs = self.embedder.embed([c.text for c in chunks])
        metas = [dict(c.metadata(), corpus_hash=corpus_hash) for c in chunks]
        self.col.add(ids=[c.chunk_id for c in chunks], documents=[c.text for c in chunks], embeddings=vecs, metadatas=metas)
        self._inventory = None

    def corpus_hash(self) -> str:
        got = self.col.get(limit=1, include=["metadatas"])
        return got["metadatas"][0]["corpus_hash"] if got["metadatas"] else ""

    def inventory(self) -> dict[tuple[str, int], set[str]]:
        """Outcome inventory from chunk metadata: (subject, grade) -> outcome IDs present in the index."""
        if self._inventory is None:
            inv: dict[tuple[str, int], set[str]] = {}
            for md in self.col.get(include=["metadatas"])["metadatas"]:
                for g in range(1, 5):
                    if md.get(f"g{g}"):
                        inv.setdefault((md["subject"], g), set()).update(o for o in md["outcome_ids"].split(",") if o)
            self._inventory = inv
        return self._inventory

    def _hit(self, cid, doc, md, dist) -> dict:
        return {"chunk_id": cid, "text": doc, "score": round(1.0 - dist, 4) if dist is not None else None,
                "outcome_ids": [o for o in md["outcome_ids"].split(",") if o], "source_file": md["source_file"],
                "file_sha256": md["file_sha256"], "pages": md.get("pages", "")}

    def retrieve(self, query: str, subject: str, grade: int, outcome_id: str | None = None,
                 k: int = TOP_K, threshold: float = SIM_THRESHOLD, require_outcome: bool = True) -> EvidenceBundle:
        t0 = time.perf_counter()
        b = EvidenceBundle(query=query, subject=subject, grade=grade, outcome_id=outcome_id, status="ok", reason="",
                           corpus_hash=self.corpus_hash(), embed_model=self.embedder.name, threshold=threshold, top_k=k)
        subj_title = subject.capitalize()

        def refuse(status: str, reason: str) -> EvidenceBundle:
            b.status, b.reason, b.chunks = status, reason, []
            b.displayed_message = (INSUFFICIENT_MSG.format(grade=grade, subject_title=subj_title) if status == "insufficient_evidence"
                                   else f"This request is inconsistent ({reason}). Please confirm one grade and subject; "
                                        "the curriculum selection was not changed.")
            b.retrieval_latency_s = round(time.perf_counter() - t0, 4)
            return b.freeze()

        # 1. Conflicting grade or subject (Doc 3 T7): never silently change the curriculum selection.
        if outcome_id:
            og, osub = outcome_grade_subject(outcome_id)
            if (og is not None and og != grade) or (osub is not None and osub != subject):
                return refuse("conflicting_request", f"outcome {outcome_id} is Grade {og} {osub}, request is Grade {grade} {subject}")
        if not 1 <= grade <= 4:
            return refuse("insufficient_evidence", f"grade {grade} outside corpus scope (Cycle 1, Grades 1-4)")
        # 2. Coverage gate on the outcome inventory BEFORE any similarity search (Doc 3 failure protocol step 3).
        inv = self.inventory().get((subject, grade), set())
        if not inv:
            return refuse("insufficient_evidence", f"no indexed evidence for Grade {grade} {subject}")
        if outcome_id is None and require_outcome:
            return refuse("insufficient_evidence", "no outcome ID given, so coverage cannot be confirmed (similarity alone does not prove coverage)")
        if outcome_id is not None and outcome_id not in inv:
            return refuse("insufficient_evidence", f"outcome {outcome_id} not in the Grade {grade} {subject} outcome inventory")
        # 3. Outcome filter: chunks that contain the requested outcome come first (DEC 013) ...
        where = {"$and": [{"subject": subject}, {f"g{grade}": True}]}
        qv = self.embedder.embed([query])
        packet: list[dict] = []
        if outcome_id:
            res = self.col.query(query_embeddings=qv, n_results=k, where=where, where_document={"$contains": f"[{outcome_id}]"},
                                 include=["documents", "metadatas", "distances"])
            packet = [self._hit(*x) for x in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])]
            packet = [h for h in packet if outcome_id in h["outcome_ids"]]
            if not packet:
                return refuse("insufficient_evidence", f"outcome {outcome_id} listed but no chunk text contains it")
        # ... then the remaining slots are filled by similarity within the same grade and subject.
        res = self.col.query(query_embeddings=qv, n_results=k + len(packet), where=where, include=["documents", "metadatas", "distances"])
        have = {h["chunk_id"] for h in packet}
        fill = [self._hit(*x) for x in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
                if x[0] not in have]
        # 4. Similarity floor (DEC 008, value unchanged) applies only to requests without an outcome ID.
        if not outcome_id and (not fill or fill[0]["score"] < threshold):
            return refuse("insufficient_evidence", f"best similarity {fill[0]['score'] if fill else None} below threshold {threshold}")
        b.chunks = (packet + fill)[:k]  # fixed order: outcome chunks (by score), then similarity fill (by score)
        b.retrieval_latency_s = round(time.perf_counter() - t0, 4)
        return b.freeze()
