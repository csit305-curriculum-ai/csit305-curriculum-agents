# Generative AI use

This file is an honest record for the CSIT305 academic-integrity requirements and follows on from Doc 3 AI 002.

**What happened.** On 2 Nov 2026, Sanjay asked a GenAI assistant (Grok Bot) to start building his part of the artefact, using the group's project documents (Document 3 v0.2 and earlier shared docs) as the outline. The assistant did the following:
- found and downloaded the sources;
- wrote all of the code in `src/`, `scripts/` and `tests/`;
- drafted `tasks.yaml` and every Markdown document;
- ran the tests and the one live smoke test;
- made the git commits under Sanjay's name.

The commits do not mean Sanjay wrote the code by hand.

| Piece | Written by | How it was verified | Still needed from Sanjay or the group |
|---|---|---|---|
| Corpus fetch and parser | AI | SHA-256 hashes recorded; record counts checked; sample rows inspected by eye against the PDF text | Sanjay to spot-check 10 Grade 3–4 rows against the PDF |
| Chunking | AI | Unit tests for window size and overlap, grade/subject separation, ID uniqueness and hash change | Review |
| Retrieval and gate | AI | Unit tests with a deterministic fake embedder, 2 tests on the real bge-m3 index, threshold calibration, gate check on all 24 tasks | Group decision on G4M-05 (DEC 008) |
| Schema, conditions A and B, retry and timeout | AI | Mocked tests for malformed JSON, invented IDs, missing citations, wrong grade, retry-once, timeout, and no LLM call after gate failure; one live smoke test | Manual tests (TESTING.md stub list) |
| tasks.yaml | AI draft | Count and structure checked against Doc 3 T3; gate check | **Group review of every task** |
| Docs | AI draft | Cross-checked against Doc 3 T3/T4/T8/T9 | Edit into your own words where you will be marked on them |

The tests were written by the same assistant that wrote the code, so they share its blind spots. The independent check is the manual test list in TESTING.md.
