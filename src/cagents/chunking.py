"""Token-window chunking: ~400 embedding-tokenizer tokens with 80-token overlap (Doc 3 T4).

Records are grouped by (source, subject, grade set) so a chunk never mixes grades or subjects;
this keeps the grade/subject filters exact. Each line keeps its outcome ID in brackets so
citations can be traced back to the source row.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

CHUNK_TOKENS = 400
OVERLAP_TOKENS = 80


class Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...
    def decode(self, ids: list[int]) -> str: ...


@dataclass
class Chunk:
    chunk_id: str
    text: str
    subject: str
    grades: list[int]
    source_file: str
    file_sha256: str
    outcome_ids: list[str] = field(default_factory=list)
    n_tokens: int = 0
    pages: list[int] = field(default_factory=list)

    def metadata(self) -> dict:
        md = {"subject": self.subject, "source_file": self.source_file, "file_sha256": self.file_sha256,
              "outcome_ids": ",".join(self.outcome_ids), "n_tokens": self.n_tokens,
              "pages": ",".join(map(str, self.pages))}
        for g in range(1, 5):  # Chroma metadata cannot hold lists, so one boolean per grade
            md[f"g{g}"] = g in self.grades
        return md


def window(ids: list[int], size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[tuple[int, int]]:
    if size <= overlap:
        raise ValueError("chunk size must exceed overlap")
    if not ids:
        return []
    spans, start, step = [], 0, size - overlap
    while True:
        end = min(start + size, len(ids))
        spans.append((start, end))
        if end == len(ids):
            return spans
        start += step


def chunk_records(records: list[dict], tok: Tokenizer, size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[Chunk]:
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault((r["source_file"], r["subject"], tuple(r["grades"])), []).append(r)
    chunks: list[Chunk] = []
    for (src, subject, grades), recs in groups.items():
        text = "\n".join(f"[{r['outcome_id']}] ({r['domain']}) {r['text']}" for r in recs)
        ids = tok.encode(text)
        pages_of: dict[str, set] = {}
        for r in recs:
            if r.get("page") is not None:
                pages_of.setdefault(r["outcome_id"], set()).add(r["page"])
        gtag = "g" + "".join(map(str, grades))
        for n, (a, b) in enumerate(window(ids, size, overlap)):
            piece = tok.decode(ids[a:b]).strip()
            oids = sorted(set(re.findall(r"\[([A-Z]+-[\w.\-]+)\]", piece)))
            chunks.append(Chunk(
                chunk_id=f"{src.split('_')[0]}-{subject[:2]}-{gtag}-{n:03d}",
                text=piece, subject=subject, grades=list(grades), source_file=src,
                file_sha256=recs[0]["file_sha256"],
                outcome_ids=oids, n_tokens=b - a, pages=sorted({p for o in oids for p in pages_of.get(o, ())})))
    return chunks


def corpus_hash(chunks: list[Chunk]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.chunk_id.encode() + b"\0" + c.text.encode() + b"\0")
    return h.hexdigest()


class WhitespaceTokenizer:
    """Deterministic test tokenizer (one token per whitespace-separated word)."""

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self.inv: dict[int, str] = {}

    def encode(self, text: str) -> list[int]:
        out = []
        for w in text.replace("\n", " \n ").split(" "):
            if w == "":
                continue
            if w not in self.vocab:
                self.vocab[w] = len(self.vocab)
                self.inv[self.vocab[w]] = w
            out.append(self.vocab[w])
        return out

    def decode(self, ids: list[int]) -> str:
        return " ".join(self.inv[i] for i in ids).replace(" \n ", "\n")
