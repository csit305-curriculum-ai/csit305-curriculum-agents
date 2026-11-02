# Curriculum agents: single-call vs retrieval-grounded vs multi-agent lesson planning (CSIT305 AT2)

This repository is the research artefact for this paper. The paper compares lesson plans for UAE MoE Cycle 1 (Grades 3–4, Maths and Science, English) produced three ways:

- **A**: one LLM call, no retrieval.
- **B**: one LLM call grounded in a frozen curriculum evidence packet.
- **C**: four specialist calls (planning, differentiation, assessment, feedback) sharing the identical packet.

The design follows Document 3 v0.3 (2 Nov 2026). This repository contains Sanjay's parts (corpus and source manifest, retrieval, conditions A and B) and, on branch `condition-c`, an AI-written Condition C pending Manzi's review (see below and AI_USE.md). Scoring (Manzi, Sameer, Mousa) is still to come.

## Architecture (Doc 3 ARCH 002)
```
tasks.yaml ─► retrieval (once per task) ─► frozen EvidenceBundle (top-5 chunk IDs + SHA-256)
                  │ coverage gate: below threshold / outcome absent ─► insufficient_evidence (no LLM call)
                  ▼
     Condition A: prompt only ─┐
     Condition B: prompt + E ──┼─► DeepSeek (deepseek-flash, thinking off, T=0.3, max 2,400 tokens)
     Condition C: 4 × (prompt + identical E) [not built yet]
                               ▼
     JSON schema + citation check ─► one regeneration on failure ─► JSONL trace + summary.csv
```
| Module | Role |
|---|---|
| `src/cagents/corpus.py` | Extracts English outcome records from the PDFs (Arabic stripped) |
| `src/cagents/chunking.py` | 400-token windows with 80 overlap, using the bge-m3 tokenizer; one grade and subject per chunk |
| `src/cagents/retrieval.py` | bge-m3 embeddings, Chroma (cosine), top 5 with grade/subject filters, coverage gate, frozen bundle hash |
| `src/cagents/schema.py` | Pydantic output schema; rejects invented or missing chunk-ID citations |
| `src/cagents/llm.py` | `DeepSeekClient` (OpenAI SDK) and `MockClient`; cost calculation |
| `src/cagents/conditions.py` | Conditions A and B, retry and timeout rules, JSONL logging |
| `src/cagents/run.py` | CLI that writes `trace.jsonl`, `summary.csv` and `bundle_<task>.json` |

## Tools and versions
- Python 3.11.18 (uv venv); exact pins are in `requirements.txt`.
- Key packages: torch 2.15.0+cpu, sentence-transformers 6.2.0, transformers 5.22.1, chromadb 1.5.9, pydantic 2.14.2, openai 3.42.1, pytest 9.2.0.
- Embedding model: BAAI/bge-m3 (HF snapshot 5617a9f6), running on CPU (about 2.9 GB RAM).
- LLM: DeepSeek `deepseek-flash` (served as DeepSeek-V4.1-Flash-1017 on 2 Nov 2026).
- PDF text: poppler `pdftotext -layout`.

## Setup and reproduction
```bash
uv venv --python 3.11 .venv && uv pip install --python .venv -r requirements.txt   # torch from the CPU index
cp .env.example .env    # add DEEPSEEK_API_KEY (never commit .env)
scripts/fetch_corpus.sh # downloads raw PDFs; check the hashes against corpus/SOURCES.md
cd src && ../.venv/bin/python -m cagents.build_index      # records -> chunks -> Chroma
../.venv/bin/python ../scripts/calibrate_threshold.py     # optional: re-check DEC 008
cd .. && .venv/bin/python -m pytest -v                    # no API calls
cd src && ../.venv/bin/python -m cagents.run --tasks G3M-P1 --conditions A B --repeats 1 --out runs/smoke
```
The full experiment (20 tasks × 3 conditions × 3 repeats) has **not** been run.

## Demo (Week 6)
`demo/app.py` is a Streamlit app. For a task from `tasks.yaml` it runs **live local retrieval** (bge-m3 + Chroma, top-5) and the
**coverage gate** (DEC 013), shows the chunks with scores, checks the live packet hash against the frozen packet, then shows
Condition A and B outputs side by side. Outputs are **replayed** from recorded runs (`runs/smoke_2`, `runs/smoke`), clearly
labelled, and **no API call is made**. Tasks with no recorded run say "No recorded run". The TEST001 entry replays the
signature failure test (B refused 10/10). The Condition C panel shows the **offline / scripted** C run (TEST 006): four-agent trace, assembled pack and token estimates.
```bash
uv pip install --python .venv -r requirements-demo.txt
.venv/bin/streamlit run demo/app.py            # Windows: .venv\Scripts\streamlit run demo\app.py
# opens http://localhost:8501
```
Needs the index built first (see Setup). Full lesson text comes from `runs/*/trace.jsonl`, which is kept locally (MoE text, git-ignored);
without it the app shows status/tokens from `summary.csv` only. `-- --live` enables new DeepSeek calls; it is off by default and
must not be used until the MoE licence is confirmed. Screenshots: `docs/demo/`.

## Condition C (four agents)
`src/cagents/condition_c.py`: planning → differentiation → assessment → feedback, plain Python (DEC 017). Every node gets the same frozen
packet as B plus the earlier drafts it needs; 800 output tokens per node (DEC 018); same model settings, validation and one regeneration
(DEC 020); coverage gate before any call; Python assembles the pack, no fifth call (DEC 019); every call logged to JSONL with per-job totals.
```bash
cd src && ../.venv/bin/python -m cagents.run run --tasks G3M-P1 --conditions A B C --out runs/x   # live (NOT until licence confirmed)
cd src && ../.venv/bin/python -m cagents.run run --tasks G3M-P1 --conditions C --scripted --out runs/c_offline   # offline
```
**Status:** written by Grok Bot at Sanjay's request on 2 Nov 2026, pending Manzi's review and ownership. Only run offline with
scripted responses (TEST 006, DEC 021); no real C output exists yet.

## Limitations (current state)
- Science outcomes come from the MoE Science Standards 2017 (English G3–4 outcomes, DEC 016). TIMSS is context only (DEC 012). All 24 tasks pass the gate.
- Run order: `python -m cagents.build_index`, then `python -m cagents.run freeze`, then `python -m cagents.run run ...`.
- Maths text extraction is heuristic. Some rows lose words that wrap across blank lines, chapter and lesson titles are mixed into the outcome text, and some outcome IDs in the source are misnumbered (e.g. `MA-5.5.9.1` appears inside the Grade 4 block).
- The similarity-only gate was calibrated on 27 hand-written queries. In the gate check (TEST 004) it refused 3 of 24 draft tasks, including a false refusal of a valid maths task (G4M-05, 0.499 vs 0.50). It was replaced by an outcome-inventory gate (DEC 013); all 24 draft tasks pass the current gate.
- Tests: 58 collected, 58 pass (`pytest`, 2 Nov 2026), including 16 Condition C tests.
- The NLI checker, scoring and statistics are not implemented here. Condition C has only been run offline with scripted responses (no real model output yet).
- Model outputs are non-deterministic even at T=0.3. Repeats are part of the design.
