# Evidence log

This log continues Document 3 v0.2 T8. ARCH 002, DEC 001–005, TEST 001 and AI 002 are in Doc 3. All times are UTC+4. Commit SHAs refer to this repository.

| ID | Date | Type | Summary | Evidence | Status |
|---|---|---|---|---|---|
| ARCH 003 | 2 Nov 2026 | Architecture | Implemented the retrieval-once pipeline for A and B: corpus → 400/80 chunks → bge-m3 → Chroma → top 5 → coverage gate → frozen bundle with SHA-256 → generation → schema and citation check → JSONL plus CSV | README; commits 3ea32c4, ef95a80 | Built |
| DEC 006–011 | 2 Nov 2026 | Decisions | Corpus scope, science gap, threshold 0.50, chunk grouping, output contract, no committing of source text | DESIGN_DECISIONS.md | Draft, needs group review |
| SRC 001 | 2 Nov 2026 | Corpus | 3 source files fetched and hashed; the MoE originals are 404, so Wayback copies were used | corpus/SOURCES.md | Done |
| TEST 002 | 2 Nov 2026 | Unit tests | 25 pytest tests (chunking, retrieval, not-covered path, schema, retry, timeout, real-index): 25 passed | TESTING.md; commit 07b5ac2 | Passed |
| TEST 003 | 2 Nov 2026 | Coverage calibration | 15 in-scope and 12 out-of-scope queries, used to set the threshold | corpus/processed/calibration.json | Done |
| TEST 004 | 2 Nov 2026 | Task gate check | All 24 draft tasks run through the gate: 21 pass, 3 refused (1 false refusal: G4M-05) | TESTING.md | Finding logged for the group |
| TEST 005 | 2 Nov 2026 10:44 | Live smoke test | G3M-P1 (pilot), A and B, 1 run each, real DeepSeek API. Both valid on the first attempt. A: 280 in / 1,521 out tokens, 12.5 s. B: 2,523 in / 1,118 out tokens, 8.0 s, cited 1 of 5 bundle chunks. Total US$0.0040 at peak rate | runs/smoke/summary.csv, trace_redacted.jsonl; commit 07b5ac2 | Passed (integration only, not a result) |
| TEST 001 | 2 Nov 2026 | Missing-outcome test | Provisional Maths variant (DEC 015): MA-4.2.5.1 removed from a copy; 10/10 B attempts refused with the expected message and no generation call. Science version with C still blocked (DEC 012) | runs/test001/; commit 1558338 | Provisional pass |
| AUDIT 001 | 2 Nov 2026 | Alignment audit | Repo checked against Doc 3 v0.2; 11 mismatches fixed (F1–F11), 36 tests pass | TESTING.md; commits 463a18f–1558338 | Done; DEC 012–015 need group review |
| AI 003 | 2 Nov 2026 | GenAI use | A GenAI assistant wrote the code, tests, docs and draft tasks; see AI_USE.md | AI_USE.md | Verification partly done |
| SRC 002 | 2 Nov 2026 | Science source found | MoE Science Standards 2017 (English G3–4 outcomes) fetched via Wayback, sha256 0012128f…, indexed; gate 24/24 | corpus/SOURCES.md; DEC 016; commits 918c194, 9bb15b1, 7473796 | Done; topics and licence need group review |
| TEST 001-S | 2 Nov 2026 | Missing-outcome test, Grade 4 Science | SC-4.4.3.2.2 removed from a copy; 10/10 B refused, no generation call | runs/test001_science; commit 18912be | B done; 10 C pending |
