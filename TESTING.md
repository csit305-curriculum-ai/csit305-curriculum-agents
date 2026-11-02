# Testing

Run with `.venv/bin/python -m pytest -v`. The suite makes no API calls; the real-index tests are skipped if `index/` has not been built.

## Run 1: 2 Nov 2026, 10:46 UTC+4, commit c72a3c8, Python 3.11.18, pytest 9.2.0
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
- Commit 4495a0c accidentally tracked `corpus/processed/records.jsonl`, which contains extracted MoE text. Fixed in 505f3db (untracked and gitignored, DEC 011).
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

## Manual tests: to be written by Sanjay (stub list)
These are deliberately not AI-written. Record the date, commit SHA and result for each.
- [ ] M1: Pick 10 random Grade 3–4 rows in `records.jsonl` and compare them with the PDF. Is the wording and outcome ID correct?
- [ ] M2: Edit one byte of a raw PDF, rerun `build_index`, and confirm the corpus hash changes and old bundles fail `verify()`.
- [ ] M3: Read the smoke-test B output. Does each cited chunk actually support the claim citing it?
- [ ] M4: Ask for a Grade 3 maths outcome that does not exist (e.g. MA-3.99.1.1) through `run.py` and confirm no API call happens (check trace.jsonl).
- [ ] M5: Hand-craft a model output citing a real chunk ID from a *different* task's bundle and confirm it is rejected.
- [ ] M6: Run condition A twice on the same task and compare outputs, to see repeat variability before the 3-repeat design.
- [ ] M7: Conflicting grade/subject task (e.g. Grade 3 task with a Grade 4 outcome ID): confirm the expected behaviour and decide the rule (Doc 3 edge case).
