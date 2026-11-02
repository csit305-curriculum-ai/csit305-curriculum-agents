# Design decisions

These continue the numbering in Document 3 v0.2 T8 (DEC 001–005 are recorded there and not repeated here). Each entry is drafted by Sanjay and still needs group review.

## DEC 006: Corpus scope and parsing (2 Nov 2026)
- **Decision:** Index MoE Maths Scope and Sequence rows for Grades 1–4 (English column only, Arabic stripped), plus two TIMSS 2023 UAE summaries. Tasks use Grades 3–4 only (Doc 3 T3). Grades 1–2 stay in the index as same-subject distractors.
- **Why:** These are the only public English sources with MoE outcome IDs that were found. Keeping Arabic out matches DEC 003 (English NLI).
- **Risk:** Extraction is heuristic (see README Limitations).

## DEC 007: Science framework not indexed (2 Nov 2026)
- **Decision:** The MOE Science Framework 2019-20 is fetched and hashed but not indexed. Its Grade 1–12 outcomes are Arabic only (checked page by page: pages 14–77 have no English words).
- **Fallback:** Science uses the English TIMSS 2023 Cycle 1 content (Exhibit 3). It carries no outcome IDs, so science tasks have `outcome_id: null`.
- **Open:** The group must choose option (a), (b) or (c) in `corpus/SOURCES.md`. TEST 001 as written (a Grade 4 Science outcome) cannot run on this corpus.

## DEC 008: Coverage-gate similarity threshold = 0.50 cosine (2 Nov 2026)
- **Evidence:** `corpus/processed/calibration.json`, from `scripts/calibrate_threshold.py` using bge-m3 on the built index.
  - 15 in-scope queries: top-1 similarity min 0.523, mean 0.583.
  - 12 off-curriculum or wrong-level queries: max 0.529 ("derivatives and integrals in calculus", Grade 4 maths), mean 0.391.
- **Decision:** 0.50. It passes every in-scope query and rejects 11 of 12 out-of-scope queries.
- **Second gate:** When a task names an outcome ID, that ID must appear in the retrieved chunks. This catches near-topic, wrong-level requests that similarity alone misses.
- **Known cost:** On the 24 draft tasks, 3 are refused: G4M-05 at 0.499, G3S-05 at 0.434, G4S-03 at 0.492. G4M-05's topic (money) *is* in the corpus, so that is a false refusal. The group should decide whether to reword the task, lower the threshold to about 0.48, or skip the similarity floor when the requested outcome ID is retrieved. Any change must be logged as a new DEC before main runs, not tuned on main tasks.
- **Fallback note:** bge-m3 ran on the box CPU (peak RSS about 2.9 GB; full index build took 48 s), so no embedding fallback was needed.

## DEC 009: One chunk = one source/subject/grade group (2 Nov 2026)
- **Decision:** Chunks are 400 bge-m3 tokens with 80 overlap, cut inside each (source, subject, grade set) group. Grade and subject filters are exact Chroma metadata filters (`g1`..`g4` booleans, because Chroma has no list metadata).
- **Result:** 52 chunks in total.

## DEC 010: Output contract for A and B (2 Nov 2026)
- **Format:** JSON with `status`, objectives, activities, differentiation (support/extension), assessment, feedback and reason. Every objective, activity and assessment item carries `citations`.
- **Condition A:** Must cite nothing.
- **Condition B:** Must cite at least one ID, and every ID must be in its frozen bundle.
- **On failure:** Any violation triggers one regeneration with the error message. Both attempts are counted and logged.
- **Timeout:** One bounded retry, then `incomplete`.
- **Gate failure:** A failed gate means no LLM call (`generation_called: false`).
- **API settings:** `response_format=json_object` and `thinking: disabled` via `extra_body` (per api-docs.deepseek.com, read 2 Nov 2026).

## DEC 011: Raw and derived source text not committed (2 Nov 2026)
- **Decision:** No licence is stated for the source files, so raw PDFs, extracted `records.jsonl`, full traces and bundles (which contain source text) are gitignored and reproduced locally.
- **Committed instead:** Hashes, the chunk manifest (IDs and token counts only), the calibration results and a redacted trace.
