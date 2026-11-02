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


def n_pages(path: Path) -> int:
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


def parse_math(path: Path) -> list[dict]:
    # Parse page by page: preserves page numbers (Doc 3 corpus metadata) and source boundaries.
    # Whole-document parsing merged blocks across form feeds and lost 27 rows (TESTING.md, audit fix).
    recs = []
    for pg in range(1, n_pages(path) + 1):
        for r in parse_math_rows(pdf_text(path, pg, pg)):
            r["page"] = pg
            recs.append(r)
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
        out.append({"subject": "maths", "grades": [4], "domain": "TIMSS Exhibit 1", "outcome_id": "TIMSS-MA-G4", "text": clean(m.group(1)), "page": None})
    s = re.search(r"(The Science Curriculum in Primary and Lower Secondary Grades.*?)Exhibit 4:", t, re.S)
    if s:
        out.append({"subject": "science", "grades": [1, 2, 3, 4], "domain": "TIMSS Exhibit 3 (Cycle 1)", "outcome_id": "TIMSS-SC-C1", "text": clean(s.group(1)), "page": None})
    return out


SCI_CODE = re.compile(r"^G([34])\.(\d)\.(\d)\.(\d+)\.(\d+)$")
SCI_DOMAINS = {"1": "Nature of Science and Technology", "2": "Earth and Space Sciences", "3": "Life Sciences", "4": "Physical Sciences"}
SCI_PAGES = range(51, 64)  # Grade 3 (pp. 51-56) and Grade 4 (pp. 57-63); Grades 1-2 are Arabic-only in this file


def _bbox_words(path: Path, pg: int) -> list[tuple[float, float, float, str]]:
    import html
    x = subprocess.run(["pdftotext", "-bbox", "-f", str(pg), "-l", str(pg), str(path), "-"], capture_output=True, text=True, check=True).stdout
    return [(float(a), float(b), float(c), html.unescape(t)) for a, b, c, t in
            re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="[\d.]+">([^<]*)</word>', x)]


def parse_science_standards(path: Path) -> list[dict]:
    """MoE Science National Curriculum Standards KG-12 (2017). Grade 3-4 learning outcomes are in English in the
    left column, with a five-part code (e.g. G3.2.3.3.2) in the next column. Uses word coordinates so the
    outcome column is not cut off by the neighbouring standard column. Arabic headers are ignored."""
    recs, cur = [], None
    for pg in SCI_PAGES:
        W = _bbox_words(path, pg)
        codes = [w for w in W if SCI_CODE.match(w[3])]
        if not codes:
            continue
        xs = [w[0] for w in codes]
        xc = max(xs, key=lambda v: sum(abs(v - u) < 8 for u in xs))  # x of the outcome-code column
        col = sorted((w for w in codes if abs(w[0] - xc) < 8), key=lambda w: w[1])
        left = sorted((w for w in W if w[2] < xc - 2 and not ARABIC.search(w[3])), key=lambda w: (round(w[1]), w[0]))
        lines: list[list] = []
        for w in left:
            if lines and abs(lines[-1][0] - w[1]) < 3:
                lines[-1][1].append(w)
            else:
                lines.append([w[1], [w]])
        used: set[int] = set()
        for y, ws in lines:
            toks = [w[3] for w in sorted(ws, key=lambda w: w[0])]
            if re.fullmatch(r"\d+", " ".join(toks)):
                continue  # page number
            start = None
            if SCI_CODE.match(toks[0]):
                start, toks = toks[0], toks[1:]  # code written inline at the start of the outcome
            else:
                for i, c in enumerate(col):
                    if i not in used and abs(c[1] - y) < 4:
                        start = c[3]; used.add(i); break
            if start:
                cur = {"code": start, "page": pg, "text": " ".join(toks)}
                recs.append(cur)
            elif cur:
                cur["text"] += " " + " ".join(toks)
    out, seen = [], set()
    for r in recs:
        text = clean(r["text"])
        if out and out[-1]["text"].endswith(",") and text[:1].islower():  # a sentence split across two code rows
            out[-1]["text"] += " " + text
            continue
        m = SCI_CODE.match(r["code"])
        key = (r["code"], text)
        if len(text) < 15 or key in seen:  # the source repeats some outcomes on consecutive rows
            continue
        seen.add(key)
        out.append({"subject": "science", "grades": [int(m.group(1))], "domain": SCI_DOMAINS.get(m.group(2), m.group(2)),
                    "outcome_id": "SC-" + r["code"][1:], "text": text, "page": r["page"]})
    return out


# role "evidence" = indexed for generation; "context" = parsed for the paper's background only.
# Doc 3: "the TIMSS chapter is contextual evidence and is not a substitute for those files" (DEC 012).
SOURCES = {
    "moe_math_scope_sequence_g1-12.pdf": (parse_math, "evidence"),
    "moe_science_standards_2017_kg-12.pdf": (parse_science_standards, "evidence"),  # DEC 016
    "timss2023_uae_encyclopedia.pdf": (parse_timss, "context"),
    # moe_science_framework_2019-20.pdf: Grades 1-4 outcomes are Arabic-only (DEC 007); hashed, not parsed.
}
MANIFEST = ROOT / "corpus" / "manifest.json"


def verify_sources(raw: Path = RAW, manifest: Path = MANIFEST) -> dict:
    """Doc 3 T7: a source-file hash mismatch blocks use until the source is revalidated."""
    import json as _j
    expected = _j.loads(manifest.read_text())["files"]
    for fname, meta in expected.items():
        got = sha256(raw / fname)
        if got != meta["sha256"]:
            raise RuntimeError(f"Source hash mismatch for {fname}: expected {meta['sha256'][:12]}, got {got[:12]}. Revalidate before use.")
    return expected


def build(raw: Path = RAW, out: Path = OUT) -> list[dict]:
    records = []
    for fname, (parser, role) in SOURCES.items():
        path = raw / fname
        h = sha256(path)
        for i, r in enumerate(parser(path)):
            r.update({"doc_id": fname.rsplit(".", 1)[0], "source_file": fname, "file_sha256": h, "record_no": i, "role": role})
            records.append(r)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_inventory(records)
    return records


def write_inventory(records: list[dict]) -> None:
    """Outcome inventory (IDs, grade, subject, domain, page; no source wording, see DEC 011)."""
    import csv
    path = ROOT / "corpus" / "processed" / "outcome_inventory.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["outcome_id", "subject", "grades", "domain", "source_file", "page", "role"])
        for r in records:
            w.writerow([r["outcome_id"], r["subject"], "|".join(map(str, r["grades"])), r["domain"], r["source_file"], r.get("page"), r["role"]])


def evidence_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("role") == "evidence"]


if __name__ == "__main__":
    recs = build()
    from collections import Counter
    print(len(recs), Counter((r["subject"], tuple(r["grades"])) for r in recs))
