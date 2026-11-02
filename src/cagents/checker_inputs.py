"""Pack -> checker interface (Doc 3 T4 "Pack to checker"): one row per citable item, with the cited passage text.

Python-side labels only (missing citation, invalid ID). NLI scoring, eligible-claim extraction and splitting
rules belong to the scoring workstream and are frozen in the pilot; this module only supplies the inputs.
"""
from __future__ import annotations

from .retrieval import EvidenceBundle
from .schema import TeachingPack, cited_items, item_text


def checker_rows(run_id: str, pack: TeachingPack | dict, bundle: EvidenceBundle | None) -> list[dict]:
    if isinstance(pack, dict):
        pack = TeachingPack.model_validate(pack)
    passages = {c["chunk_id"]: c for c in (bundle.chunks if bundle else [])}
    rows = []
    for section, ref, item in cited_items(pack):
        cites = list(item.citations)
        valid = [c for c in cites if c in passages]
        rows.append({
            "run_id": run_id, "section": section, "item_ref": ref, "text": item_text(item),
            "objective_ids": getattr(item, "objective_ids", [getattr(item, "objective_id", None)]),
            "cited_ids": cites, "invalid_ids": [c for c in cites if c not in passages],
            "missing_citation": not cites,
            "passages": [{"chunk_id": c, "text": passages[c]["text"], "source_file": passages[c]["source_file"],
                          "pages": passages[c]["pages"]} for c in valid],
            "bundle_hash": bundle.bundle_hash if bundle else None,
        })
    return rows
