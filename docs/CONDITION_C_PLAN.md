# Condition C plan (scaffold for Manzi)

**Owner: Manzi** (Doc 3 contribution table: Condition C, interface and logging).
This file is a starting plan only. No Condition C code exists in this repository yet. The design, code, commits and the oral-defence explanation of Condition C must be Manzi's own work. Change anything here; record changes as DEC entries.
Written 2 Nov 2026 by a GenAI assistant at Sanjay's request (AI 003), from Document 3 v0.3 ("Agent sequence and interfaces", "Build A and B first, then the four C nodes").

## What Doc 3 already fixes
- Four specialist calls, fixed order: **planning → differentiation → assessment → feedback**. Same model as A and B (deepseek-flash, T=0.3).
- Every node gets the **identical frozen evidence packet** given to B. Agents make no extra retrieval calls. The timed C request must reproduce the frozen packet (`retrieval.assert_reproduces`); a mismatch stops the run.
- Only supplied passage IDs may be cited. Objective IDs link sections.
- Python orchestration and assembly; **no fifth generative call**.
- Same retry policy as A/B (one regeneration on invalid output; one retry after 5 s on timeout). Log per-node and whole-job status. **Never silently substitute B for a failed C run.**

## Roles and handoffs
| # | Node | Input | Output (existing model in `schema.py`) |
|---|---|---|---|
| 1 | planning | task + packet | `Planning` (objectives with IDs `O1..`, lesson_sequence) |
| 2 | differentiation | task + packet + Planning | `Differentiation` (support, extension; each links objective IDs) |
| 3 | assessment | task + packet + Planning | `Assessment` (questions `Q1..` with answer keys, linked to objectives) |
| 4 | feedback | task + packet + Planning + Assessment | `Feedback` (templates linked to question/objective IDs) |

Python assembles the four sections into the same `TeachingPack` used by A and B, so the checker (`checker_inputs.checker_rows`) and scoring treat all conditions the same.

## Suggested interface (new module `src/cagents/condition_c.py`)
```python
NODES = ("planning", "differentiation", "assessment", "feedback")

def node_messages(node: str, task: dict, bundle: EvidenceBundle, upstream: dict[str, dict]) -> list[dict]: ...
def run_node(node, task, bundle, upstream, client, logger, base) -> dict:
    """Calls conditions.generate_validated with SECTION_MODELS[node]; returns {status, section, attempts, tokens, cost, latency}."""
def run_condition_c(task, client, logger, bundle, repeat=1, job_id=None, order_pos=None) -> dict:
    """Runs NODES in order; stops on the first failed node (job_status = incomplete, failed_node = ...);
    assembles TeachingPack; validates cross-section links (every objective/question ID referenced exists)."""
```
Hook into `run.py` by allowing `--conditions A B C` and dispatching C to `run_condition_c`. Keep the seeded A/B/C order shuffle.

Open decision for Manzi (log as a DEC): token budget per node (A/B use 2,400; the 2 Nov smoke re-run showed A hitting that limit twice, see TESTING.md TEST 005b).

## Logging hooks (match the A/B trace fields)
Per node: `run_id, job_id, node, task_id, condition="C", repeat, order_pos, bundle_hash, chunk_ids, attempt, prompt_tokens, completion_tokens, cached_tokens, latency_s, finish_reason, cost_usd, valid, error`.
Per job: `status, job_status, failed_node, attempts (sum), api_failures, word_count, total tokens/cost/latency (sum of nodes + retrieval)`.
`summary.csv` gets one row per job, same columns as A/B, so cost comparison is direct.

## Tests
Skipped stubs are in `tests/test_condition_c.py`. Remove each `skip` as you implement it. Use `MockClient`; no API calls in tests.

## Not covered here
The NLI checker and scoring (proposed for Sameer) and the Streamlit interface (Manzi).
