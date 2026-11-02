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


## DEC 012: TIMSS is context only, not generation evidence (2 Nov 2026, alignment audit)
- **Why:** Doc 3 Corpus: "the TIMSS chapter is contextual evidence and is not a substitute for those files". The build had indexed it as science (and G4 maths) evidence.
- **Decision:** `corpus/manifest.json` marks TIMSS `role: context`; it is parsed but not indexed. The Arabic science framework stays `not_indexed`.
- **Consequence (superseded by DEC 016):** No science evidence is indexed, so all 12 science tasks are refused by the gate until an English MoE Grade 3–4 science source is confirmed. This blocks half the 20 main tasks. **Group decision needed.**

## DEC 013: Outcome-inventory gate replaces similarity-only gate (2 Nov 2026, alignment audit). Needs group approval
- **Why:** Doc 3 failure protocol step 3 says "check the outcome inventory before generation", and Stage 1 asks for outcome filters. Similarity alone cannot show that an outcome is covered, and it falsely refused G4M-05 (TEST 004).
- **Order of checks:** (1) outcome ID grade/subject must match the request, else `conflicting_request` (Doc 3 T7: never quietly change it); (2) grade in scope; (3) the grade/subject has indexed evidence; (4) an outcome ID is required and must be in the inventory; (5) packet = chunks whose text contains the outcome ID (by score), then similarity fill to k = 5 within the same grade and subject.
- **Threshold:** The 0.50 value (DEC 008) is **not changed**. It now applies only when a caller sets `require_outcome=False` and gives no outcome ID; no study task does this.
- **Result:** All 12 maths tasks pass the gate (G4M-05 now passes); all 12 science tasks are refused (DEC 012).

## DEC 014: Output schema matches the Doc 3 pack (2 Nov 2026, alignment audit)
- **Why:** Doc 3 asks for objectives and lesson sequence, support and extension, questions with answer keys, and feedback templates, linked by objective IDs. DEC 010's schema had no answer keys, objective IDs or real feedback templates.
- **Decision:** Four sections (`planning`, `differentiation`, `assessment`, `feedback`). Objectives have `O1…` IDs; every other item lists `objective_ids` that must exist. Questions have `Q1…` IDs and `answer_key`. All items carry `citations`. Section models are exported so condition C specialists validate their own section with `parse_section` (same citation rules).
- **Retry policy (one routine for all conditions, `generate_validated`):** invalid JSON/schema/ID → one regeneration, both attempts counted; timeout, connection, 429 or 5xx error → one retry after a 5 s delay, then `incomplete` with the trace kept. After a failed format retry the last parsed output is kept as `output_candidate` so scoring can count fabricated IDs as cited but unsupported (Doc 3). Incomplete runs get `completion: 0`.
- **Supersedes:** the schema part of DEC 010.

## DEC 015: TEST 001 run provisionally on Grade 4 Maths (superseded in part by DEC 016) (2 Nov 2026, alignment audit)
- **Why:** Doc 3 specifies a Grade 4 Science outcome, which cannot be run (DEC 012).
- **Decision:** Same procedure on `MA-4.2.5.1`, condition B only (C not built). This does not replace the Science TEST 001, which must still be run once a source exists, with 10 B and 10 C attempts.

## DEC 016: English MoE Science Standards 2017 indexed as science evidence (2 Nov 2026)
- **Why:** An English source for Grade 3–4 science outcomes was found: the MoE "Science: National Curriculum Standards KG–12" (2017), linked from the DMES MoE Standards page and fetched from the Internet Archive (SRC 002, corpus/SOURCES.md). Earlier docs said no such source existed; that was wrong.
- **Decision:** Parse pp. 51–63 (English column, word coordinates) into records with `outcome_id` = `SC-` + the source code (e.g. `G4.4.3.2.2` → `SC-4.4.3.2.2`), domain from the second digit (1 Nature of Science, 2 Earth and Space, 3 Life, 4 Physical). Role `evidence`. TIMSS stays context only (DEC 012 unchanged). The Arabic 2019-20 framework stays not indexed (DEC 007).
- **Tasks:** All 12 science tasks now have outcome IDs. Topics were re-worded to match the chosen outcome (Doc 3: choose outcomes after coverage is confirmed). Codes the source reuses for different text were avoided. **Group review needed** for the topic changes.
- **Result:** Gate check (`run freeze`): 24/24 tasks pass (12 maths, 12 science). 38 tests pass. Index: 514 evidence records, 61 chunks.
- **TEST 001:** Now run on Grade 4 Science `SC-4.4.3.2.2`, as Doc 3 specifies: 10/10 B attempts refused (runs/test001_science). The 10 C attempts are still pending (C not built). The Maths run (DEC 015) is kept as an extra result.
- **Risks:** 2017 edition, may differ from the current curriculum; no licence stated; source has reused codes (see SOURCES.md).
