# Curriculum agents: single-call vs retrieval-grounded vs multi-agent lesson planning (CSIT305 AT2)

This repository is the research artefact for this paper. The paper compares lesson plans for UAE MoE Cycle 1 (Grades 3–4, Maths and Science, English) produced three ways:

- **A**: one LLM call, no retrieval.
- **B**: one LLM call grounded in a frozen curriculum evidence packet.
- **C**: four specialist calls (planning, differentiation, assessment, feedback) sharing the identical packet.

The design follows Document 3 v0.2 (26 Oct 2026). This repository currently contains Sanjay's parts: the corpus and source manifest, retrieval, and conditions A and B. Condition C and logging analysis (Manzi) and scoring (Manzi, Sameer, Mousa) are still to come.

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

## Limitations (current state)
- English Grade 3–4 Science outcomes are missing. TIMSS is context only (DEC 012), so every science task is refused until a source is found (see `corpus/SOURCES.md`).
- Run order: `python -m cagents.build_index`, then `python -m cagents.run freeze`, then `python -m cagents.run run ...`.
- Maths text extraction is heuristic. Some rows lose words that wrap across blank lines, chapter and lesson titles are mixed into the outcome text, and some outcome IDs in the source are misnumbered (e.g. `MA-5.5.9.1` appears inside the Grade 4 block).
- The similarity threshold was calibrated on only 27 hand-written queries. It refuses 3 of the 24 draft tasks, including one maths task (G4M-05) whose topic is in the corpus (see TESTING.md).
- The NLI checker, condition C, scoring and statistics are not implemented here.
- Model outputs are non-deterministic even at T=0.3. Repeats are part of the design.
