"""Verify source hashes, build records, chunks and the Chroma index. Usage: python -m cagents.build_index"""
import json

from . import corpus
from .chunking import chunk_records, corpus_hash
from .retrieval import BGEM3Embedder, HFTokenizerAdapter, Index, ROOT


def main() -> None:
    corpus.verify_sources()  # Doc 3 T7: stop if any source file changed
    records = corpus.build()
    ev = corpus.evidence_records(records)  # TIMSS is context only (DEC 012)
    emb = BGEM3Embedder()
    chunks = chunk_records(ev, HFTokenizerAdapter(emb.tokenizer))
    h = corpus_hash(chunks)
    Index(emb).build(chunks, h)
    manifest = {"n_records": len(records), "n_evidence_records": len(ev), "n_chunks": len(chunks), "corpus_hash": h,
                "embed_model": emb.name,
                "chunks": [{"chunk_id": c.chunk_id, "n_tokens": c.n_tokens, "pages": c.pages, "outcome_ids": c.outcome_ids} for c in chunks]}
    (ROOT / "corpus" / "processed" / "chunk_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"records={len(records)} evidence={len(ev)} chunks={len(chunks)} corpus_hash={h[:16]}")


if __name__ == "__main__":
    main()
