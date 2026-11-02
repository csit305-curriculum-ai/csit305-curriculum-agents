"""Turn raw source PDFs into English-only outcome records (corpus/processed/records.jsonl).

Each record: doc_id, source_file, subject, grades (list), domain, outcome_id, text, page_hint.
Arabic text is stripped because the checker and this research are English-only (Doc 3, DEC 003).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "corpus" / "raw"
OUT = ROOT / "corpus" / "processed" / "records.jsonl"

ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u200c-\u200f\u202a-\u202e]+")
MATH_ROW = re.compile(r"^\s*([1-4])\s+GEN\s+(.+?)\s{2,}(\d+\.\d+\.\d+\.\d+)\b")
TARGET_GRADES = {1, 2, 3, 4}  # Cycle 1. The study tasks use Grades 3-4 only (Doc 3 T3).


def pdf_text(path: Path, first: int | None = None, last: int | None = None) -> str:
    cmd = ["pdftotext", "-layout"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(path), "-"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def clean(s: str) -> str:
    s = ARABIC.sub(" ", s)
    s = re.sub(r"[^\x20-\x7E\u2013\u2014\u2019]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_math_rows(text: str) -> list[dict]:
    """Rows are separated by runs of blank lines; a row block holds one marker line (grade, stream, domain, outcome ID)."""
    blocks = re.split(r"\n\s*\n\s*\n", text)
    records = []
    for block in blocks:
        lines = block.splitlines()
        marker = next((MATH_ROW.match(l) for l in lines if MATH_ROW.match(l)), None)
        if not marker:
            continue
        grade = int(marker.group(1))
        if grade not in TARGET_GRADES:
            continue
        domain, oid = clean(marker.group(2)), marker.group(3)
        body = clean(" ".join(lines))
        # Drop the marker tokens so only the outcome wording (plus chapter/lesson titles) remains.
        body = re.sub(rf"^.*?{re.escape(oid)}\s*", "", body)
        body = re.sub(rf"\b{grade} GEN {re.escape(domain)} ", "", body)
        if len(body) < 8:
            continue
        records.append({"subject": "maths", "grades": [grade], "domain": domain, "outcome_id": f"MA-{oid}", "text": body})
    return records


def parse_math(path: Path) -> list[dict]:
    recs = parse_math_rows(pdf_text(path))
    seen, out = set(), []
    for r in recs:  # the source repeats an outcome on several lesson rows; keep distinct text
        key = (r["outcome_id"], r["text"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def parse_timss(path: Path) -> list[dict]:
    """TIMSS 2023 Encyclopedia (UAE): Grade 4 maths topics (Exhibit 1) and Cycle 1 science content (Exhibit 3)."""
    t = pdf_text(path)
    out = []
    m = re.search(r"Exhibit 1: Mathematics Topics for Grade 4(.*?)Exhibit 2:", t, re.S)
    if m:
        out.append({"subject": "maths", "grades": [4], "domain": "TIMSS Exhibit 1", "outcome_id": "TIMSS-MA-G4", "text": clean(m.group(1))})
    s = re.search(r"(The Science Curriculum in Primary and Lower Secondary Grades.*?)Exhibit 4:", t, re.S)
    if s:
        out.append({"subject": "science", "grades": [1, 2, 3, 4], "domain": "TIMSS Exhibit 3 (Cycle 1)", "outcome_id": "TIMSS-SC-C1", "text": clean(s.group(1))})
    return out


SOURCES = {
    "moe_math_scope_sequence_g1-12.pdf": parse_math,
    "timss2023_uae_encyclopedia.pdf": parse_timss,
    # moe_science_framework_2019-20.pdf: Grades 1-4 outcomes are Arabic-only in this file, so it is
    # fetched and hashed but not indexed (see DESIGN_DECISIONS.md DEC 007).
}


def build(raw: Path = RAW, out: Path = OUT) -> list[dict]:
    records = []
    for fname, parser in SOURCES.items():
        path = raw / fname
        h = sha256(path)
        for i, r in enumerate(parser(path)):
            r.update({"doc_id": fname.rsplit(".", 1)[0], "source_file": fname, "file_sha256": h, "record_no": i})
            records.append(r)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return records


if __name__ == "__main__":
    recs = build()
    from collections import Counter
    print(len(recs), Counter((r["subject"], tuple(r["grades"])) for r in recs))
