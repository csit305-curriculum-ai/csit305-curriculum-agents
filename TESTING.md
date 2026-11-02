# Testing

Run with `.venv/bin/python -m pytest -v`. The suite makes no API calls; the real-index tests are skipped if `index/` has not been built.

## Run 1: 2 Nov 2026, 10:46 UTC+4, commit 07b5ac2, Python 3.11.18, pytest 9.2.0
**Result: 25 passed, 0 failed, 0 skipped (6.9 s).**

| Test | Covers | Written by | Result |
|---|---|---|---|
| test_chunking::test_window_sizes_and_overlap | 400/80 windows; exact 80-token overlap | AI | pass |
| test_chunking::test_window_short_and_empty | short or empty input; size ≤ overlap rejected | AI | pass |
| test_chunking::test_chunks_never_mix_grade_or_subject | grade/subject isolation | AI | pass |
| test_chunking::test_chunk_ids_unique_and_outcomes_traced | unique IDs; outcome IDs kept | AI | pass |
| test_chunking::test_corpus_hash_changes_with_text | changed source → changed hash | AI | pass |
| test_retrieval::test_topk_respects_filters | top-k ≤ 5, grade filter, sorted scores | AI | pass |
| test_retrieval::test_science_cycle1_visible_for_grade4 | Cycle 1 science chunk reachable from Grade 4 | AI | pass |
| test_retrieval::test_bundle_hash_frozen_and_tamper_detected | deterministic hash; tampering stops the run | AI | pass |
| test_retrieval::test_out_of_scope_grade_rejected | Grade 6 → insufficient_evidence | AI | pass |
| test_not_covered::test_below_threshold_returns_insufficient | similarity floor | AI | pass |
| test_not_covered::test_missing_outcome_is_not_covered | TEST 001 mechanism (outcome removed) | AI | pass |
| test_not_covered::test_condition_b_never_calls_model_after_gate_failure | no generation after gate failure | AI | pass |
| test_schema_and_retry::test_valid_b_output_passes | valid output accepted | AI | pass |
| test_schema_and_retry::test_invalid_outputs_rejected ×6 | malformed JSON, invented ID, missing citations, A citing, grade mismatch, schema | AI | pass |
| test_schema_and_retry::test_retry_once_then_success_counts_both | one regeneration; both attempts logged with chunk IDs, tokens, latency | AI | pass |
| test_schema_and_retry::test_retry_only_once_then_invalid | no second regeneration | AI | pass |
| test_schema_and_retry::test_timeout_one_bounded_retry_then_incomplete | timeout rule | AI | pass |
| test_schema_and_retry::test_condition_a_has_no_evidence_in_prompt | A gets no evidence; max_tokens 2,400 | AI | pass |
| test_real_index::test_grade3_place_value_outcome_retrieved | real bge-m3 index finds MA-3.1.1.1 | AI | pass |
| test_real_index::test_off_curriculum_query_refused | real index refuses an off-topic query | AI | pass |

**Failures, fixes and retests.** No pytest test has failed so far, so there is no failure → fix → retest cycle to report yet. Because the tests and the code came from the same AI assistant, a clean first run is weak evidence. The manual tests below are the independent check.

Problems found outside pytest and fixed:
- Commit 3ea32c4 accidentally tracked `corpus/processed/records.jsonl`, which contains extracted MoE text. Fixed in e9a3357 (untracked and gitignored, DEC 011).
- The moe.gov.ae source links returned 404. The fetch script now uses Wayback copies (SOURCES.md).

## Gate check on draft tasks (TEST 004), 2 Nov 2026
Each of the 24 tasks in tasks.yaml was run through `Index.retrieve(topic, subject, grade, outcome_id)` at threshold 0.50.
- **Result:** 21 ok, 3 insufficient_evidence:
  - G4M-05 at 0.499: **false refusal**, money is in the corpus.
  - G3S-05 at 0.434.
  - G4S-03 at 0.492.
- **Action:** Group decision needed (DEC 008). The threshold was deliberately not changed, to avoid tuning on main tasks.

## Live smoke test (TEST 005), 2 Nov 2026, 10:44 UTC+4
- **Setup:** pilot task G3M-P1, one run each of A and B, deepseek-flash, thinking disabled, T=0.3. Peak-hour pricing applied (06:44 UTC, Monday).

| Cond. | Status | Attempts | In tokens | Out tokens | Latency | Cost (USD) | Citations |
|---|---|---|---|---|---|---|---|
| A | ok | 1 | 280 | 1,521 | 12.5 s | 0.001909 | none (as required) |
| B | ok | 1 | 2,523 | 1,118 | 8.0 s | 0.002099 | moe-ma-g3-000 (1 of 5 bundle chunks) |

- **Total:** US$0.0040.
- **Observations:**
  - A wrote about 1,000 words, above the 700–900 target, while B wrote about 660, below it. Treat this as a pilot prompt-tuning item, not a result.
  - B cited only one chunk.
- **Files:** runs/smoke/summary.csv and runs/smoke/trace_redacted.jsonl. The full trace is kept locally only.

## Live smoke test re-run (TEST 005b), 2 Nov 2026, 11:29 UTC+4
- **Why:** TEST 005 used the old schema. Same setup (G3M-P1, one run each of A and B, deepseek-flash, T=0.3, max 2,400 tokens), current four-section schema, peak pricing.

| Cond. | Status | Attempts | In tokens | Out tokens | Latency | Cost (USD) | Citations |
|---|---|---|---|---|---|---|---|
| B | ok | 1 | 2,805 | 1,782 | 10.8 s | 0.002980 | moe-ma-g3-000 (1 of 5 bundle chunks) |
| A | invalid_output | 2 | 3,351 | 4,800 | 23.2 s | 0.005975 | none |

- **Total:** US$0.0090.
- **Finding (failure):** A hit the 2,400-token limit on both attempts (`finish_reason=length`), so its JSON was cut off and it was logged as invalid_output after one regeneration, as designed. B passed at 656 words.
- **Fix needed (group decision, not applied):** raise the A/B (and per-node C) output limit or tighten the length instruction, then retest in the pilot. Not changed here, to avoid tuning on one run.
- **Observation:** B again cited only one of five chunks.
- **Files:** runs/smoke_2/summary.csv and runs/smoke_2/trace_redacted.jsonl (prompts and outputs redacted; full trace kept locally).
- **Disclosure:** this re-run again sent MoE Mathematics excerpts to the DeepSeek API before reuse terms were confirmed (enquiry to MoE drafted, not yet sent). No further API calls until terms are confirmed.

## Alignment audit against Doc 3 (2 Nov 2026, 10:51–12:00 UTC+4)
A GenAI assistant re-read Doc 3 v0.2 in full and checked the repo against it. Mismatches found, fixed and retested:

| # | Failure found | Fix (commit) | Retest |
|---|---|---|---|
| F1 | TIMSS indexed as generation evidence, against Doc 3 Corpus | Marked context only, not indexed (463a18f, DEC 012) | `test_timss_context_never_retrieved` passes (test renamed under SRC 002) |
| F2 | No page numbers in records or packets (Doc 3 metadata list) | Per-page parsing; chunks carry `pages` (463a18f) | `test_outcome_chunk_carries_pages` passes |
| F3 | Whole-document parsing silently lost 27 outcome rows across page breaks (408 vs 435) | Per-page parsing (463a18f) | 435 evidence rows; inventory in corpus/processed/outcome_inventory.csv |
| F4 | No source-hash check before use (Doc 3 T7 "hash mismatch blocks use") | `verify_sources()` against corpus/manifest.json in build, freeze, run (463a18f) | Called on every build/freeze/run; M2 manual test still to do |
| F5 | Gate was similarity-only, no outcome inventory, no conflicting-request check | Inventory gate + conflict check (ed738ef, DEC 013) | 6 tests in test_not_covered.py pass |
| F6 | Packets were retrieved once per run, not frozen and re-checked on timed requests | `run freeze` writes packets/; each timed B request re-retrieves and `assert_reproduces` (ed738ef, 4fffe11) | `test_live_retrieval_must_reproduce_frozen_packet` passes; 12/12 maths packets reproduced in a mock run |
| F7 | Schema lacked answer keys, objective IDs, lesson sequence and feedback templates | Four-section schema (9f27336, DEC 014) | 10 schema tests pass |
| F8 | Timeout retry had no delay; other API errors crashed the run | 5 s delay; connection/429/5xx treated the same (9f27336) | `test_timeout_one_bounded_retry_with_delay_then_incomplete` passes |
| F9 | Log lacked requested model, pricing snapshot, job/node IDs, word count, retrieval latency in the total | Added (9f27336) | `test_retry_once_then_success_counts_both` checks the fields |
| F10 | A/B order not randomised | Seeded shuffle per task × repeat block (4fffe11) | Mock run showed both orders |
| F11 | No interface for the checker (Doc 3 T4 "Pack to checker") | `checker_inputs.checker_rows` (9f27336) | `test_checker_rows_include_cited_passages_and_invalid_ids` passes |

- **First retest after F1–F5 (at 463a18f, before the test rewrite):** 13 failed, 12 passed. All failures came from tests written for the old API (`exclude_outcomes`, old schema, similarity-only gate). Tests rewritten to Doc 3 behaviour, not loosened.
- **Final retest (1558338):** 36 passed.
- **The live smoke test (TEST 005) used the old schema.** It was re-run on 2 Nov 2026 (TEST 005b above).
- **Disclosure:** TEST 005 sent MoE excerpts to the DeepSeek API before the source terms were confirmed (Doc 3 Corpus). No further API calls were made.

## TEST 001 (provisional Maths variant, DEC 015), 2 Nov 2026
- **Setup:** Removed MA-4.2.5.1 from a copy of the evidence records (1 record removed); the copy has neither the record nor the ID in chunk text. Original records sha256 5ffb7c39…, modified b8ca9ba5….
- **Result:** 10/10 B attempts returned `insufficient_evidence` with the exact Doc 3 message (Maths wording), retrieved no IDs, and made no generation call.
- **Files:** runs/test001/test001_results.csv, removal_check.json. Script: scripts/test001_missing_outcome.py.
- **Still to do:** the real Grade 4 Science TEST 001 with 10 B + 10 C attempts.

## Manual tests: to be written by Sanjay (stub list)
These are deliberately not AI-written. Record the date, commit SHA and result for each.
- [ ] M1: Pick 10 random Grade 3–4 rows in `records.jsonl` and compare them with the PDF. Is the wording and outcome ID correct?
- [ ] M2: Edit one byte of a raw PDF, rerun `build_index`, and confirm the corpus hash changes and old bundles fail `verify()`.
- [ ] M3: Read the smoke-test B output. Does each cited chunk actually support the claim citing it?
- [ ] M4: Ask for a Grade 3 maths outcome that does not exist (e.g. MA-3.99.1.1) through `run.py` and confirm no API call happens (check trace.jsonl).
- [ ] M5: Hand-craft a model output citing a real chunk ID from a *different* task's bundle and confirm it is rejected.
- [ ] M6: Run condition A twice on the same task and compare outputs, to see repeat variability before the 3-repeat design.
- [ ] M7: Conflicting grade/subject task (e.g. Grade 3 task with a Grade 4 outcome ID): confirm the expected behaviour and decide the rule (Doc 3 edge case).

## SRC 002 / TEST 001 Science (2 Nov 2026)
| Step | Result |
|---|---|
| Failure | Docs claimed no English G3–4 science outcomes; all 12 science tasks refused; TEST 001 could not run as specified |
| Fix | MoE Science Standards 2017 found, hashed, parsed (79 records) and indexed (DEC 016); science outcome IDs added to tasks.yaml |
| Test change | `test_timss_not_indexed_so_science_refused` replaced by `test_grade4_science_outcome_retrieved`, `test_timss_context_never_retrieved`, `test_unknown_science_outcome_refused` (the old test asserted the gap itself) |
| Retest | 38 passed; `run freeze` 24/24 ok |
| TEST 001 (Science, B only) | `SC-4.4.3.2.2` removed from a copy (1 record); 10/10 refused with the expected Grade 4 Science message, no generation call. C pending |

Note (2 Nov 2026): commit author emails were rewritten before the first push, so every SHA changed. All SHAs in these records refer to the rewritten history on GitHub (https://github.com/csit305-curriculum-ai/csit305-curriculum-agents).
