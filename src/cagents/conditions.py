"""Conditions A (no retrieval) and B (frozen evidence packet E, chunk-ID citations). Doc 3 T2/T4/T7.

`generate_validated` is the shared call-plus-policy routine; condition C specialists must reuse it so the
retry policy is identical in every condition (Doc 3 "Additional robustness checks").
Rules:
- B never calls the model when the coverage gate failed (status insufficient_evidence / conflicting_request).
- The packet hash is verified before generation; a mismatch stops the run.
- Invalid JSON / schema / citation -> one regeneration; both attempts counted and logged.
- Timeout or transient API error -> one bounded retry after RETRY_DELAY_S, then status "incomplete", trace kept.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import llm
from .llm import MAX_TOKENS_AB, MODEL, PRICING_SNAPSHOT, LLMClient, LLMTimeout, LLMTransientError, cost_usd, is_peak
from .retrieval import EvidenceBundle
from .schema import OutputError, parse_and_check, word_count

SCHEMA_HINT = """Return ONLY one JSON object:
{"status": "ok" | "insufficient_evidence", "grade": int, "subject": "maths"|"science", "outcome_id": str|null, "title": str,
 "planning": {"objectives": [{"objective_id": "O1", "text": str, "citations": [chunk_id]}],
              "lesson_sequence": [{"step": 1, "description": str, "minutes": int, "objective_ids": ["O1"], "citations": [chunk_id]}]},
 "differentiation": {"support": [{"description": str, "objective_ids": ["O1"], "citations": [chunk_id]}],
                     "extension": [{"description": str, "objective_ids": ["O1"], "citations": [chunk_id]}]},
 "assessment": {"questions": [{"question_id": "Q1", "question": str, "answer_key": str, "objective_ids": ["O1"], "citations": [chunk_id]}]},
 "feedback": {"templates": [{"answer_pattern": str, "feedback": str, "objective_ids": ["O1"], "citations": [chunk_id]}]},
 "reason": str}
Every objective_ids entry must match an objective in planning.objectives. Feedback templates describe possible answer
patterns, never identifiable pupils. Target 700-900 words of teaching content in total."""

SYSTEM_A = ("You are a lesson-planning assistant for UAE Ministry of Education Cycle 1 teachers. Write in English. "
            "No curriculum evidence is supplied; use your general knowledge and leave every citations list empty. " + SCHEMA_HINT)

SYSTEM_B = ("You are a lesson-planning assistant for UAE Ministry of Education Cycle 1 teachers. Write in English. "
            "Use ONLY the curriculum evidence passages supplied. Cite passage IDs exactly as given (e.g. \"moe-ma-g3-004\") "
            "wherever an item depends on the curriculum; never invent IDs. If the evidence does not cover the requested "
            "outcome, return status \"insufficient_evidence\" with a reason and no sections. " + SCHEMA_HINT)


def task_prompt(task: dict) -> str:
    return (f"Task {task['task_id']}: Grade {task['grade']} {task['subject']}. Outcome: {task.get('outcome_id') or 'n/a'}. "
            f"Topic: {task['topic']}. Lesson duration: {task.get('duration_min', 45)} minutes. "
            f"Class needs: {task.get('needs', 'mixed-ability class of 25')}. "
            "Produce a complete teaching pack: objectives and lesson sequence, support and extension activities, "
            "questions with answer keys, and feedback templates.")


def evidence_block(b: EvidenceBundle) -> str:
    return "\n\n".join(f"<passage id=\"{c['chunk_id']}\" source=\"{c['source_file']}\" pages=\"{c['pages']}\">\n{c['text']}\n</passage>"
                       for c in b.chunks)


def build_messages(task: dict, condition: str, bundle: EvidenceBundle | None) -> list[dict]:
    if condition == "A":
        return [{"role": "system", "content": SYSTEM_A}, {"role": "user", "content": task_prompt(task)}]
    return [{"role": "system", "content": SYSTEM_B},
            {"role": "user", "content": f"EVIDENCE PACKET {bundle.bundle_hash[:12]}:\n{evidence_block(bundle)}\n\n{task_prompt(task)}"}]


class TraceLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, rec: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def generate_validated(client: LLMClient, logger: TraceLogger, base: dict, messages: list[dict],
                       validate: Callable[[str], object], max_tokens: int, retry_delay_s: float | None = None) -> dict:
    """One node call under the shared policy. Returns status ok/invalid_output/incomplete plus usage totals."""
    delay = llm.RETRY_DELAY_S if retry_delay_s is None else retry_delay_s
    attempts = api_failures = tok_in = tok_out = cached = 0
    lat = cost = 0.0
    status, err, parsed, candidate = "invalid_output", "", None, None
    format_retry_used = False
    while True:
        attempts += 1
        t = datetime.now(timezone.utc)
        try:
            r = client.complete(messages, max_tokens)
        except (LLMTimeout, LLMTransientError) as e:
            api_failures += 1
            logger.log(dict(base, event="api_error", attempt=attempts, error_type=type(e).__name__, error=str(e)[:500], ts=_now()))
            if api_failures > 1:
                status, err = "incomplete", f"{type(e).__name__} after one bounded retry"
                break
            time.sleep(delay)
            continue
        peak = is_peak(t.hour, t.weekday())
        c = cost_usd(r, peak)
        tok_in += r.prompt_tokens; tok_out += r.completion_tokens; cached += r.cached_tokens; lat += r.latency_s; cost += c
        rec = dict(base, event="attempt", attempt=attempts, messages=messages, raw_output=r.text, requested_model=MODEL,
                   returned_model=r.model, prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens,
                   cached_tokens=r.cached_tokens, latency_s=r.latency_s, finish_reason=r.finish_reason, peak=peak,
                   cost_usd=round(c, 6), ts_start=t.isoformat(timespec="seconds"), ts=_now())
        try:
            parsed = validate(r.text)
            status, err = "ok", ""
            logger.log(dict(rec, valid=True))
            break
        except OutputError as e:
            err = str(e)
            try:
                candidate = json.loads(r.text)  # kept for scoring (fabricated IDs still count as cited, Doc 3)
            except json.JSONDecodeError:
                candidate = None
            logger.log(dict(rec, valid=False, error=err))
            if format_retry_used:
                break
            format_retry_used = True
            messages = messages + [{"role": "assistant", "content": r.text},
                                   {"role": "user", "content": f"Your output was rejected: {err}. Return corrected JSON only."}]
    return {"status": status, "error": err, "parsed": parsed, "candidate": candidate, "attempts": attempts,
            "api_failures": api_failures, "prompt_tokens": tok_in, "completion_tokens": tok_out, "cached_tokens": cached,
            "gen_latency_s": round(lat, 3), "cost_usd": round(cost, 6)}


def run_condition(task: dict, condition: str, client: LLMClient, logger: TraceLogger, bundle: EvidenceBundle | None = None,
                  repeat: int = 1, max_tokens: int = MAX_TOKENS_AB, job_id: str | None = None, order_pos: int | None = None,
                  retry_delay_s: float | None = None) -> dict:
    if condition not in ("A", "B"):
        raise ValueError("this module implements conditions A and B only; C reuses generate_validated")
    t_job = time.perf_counter()
    run_id = uuid.uuid4().hex[:12]
    base = {"run_id": run_id, "job_id": job_id or run_id, "node": "single", "task_id": task["task_id"], "condition": condition,
            "repeat": repeat, "order_pos": order_pos, "grade": task["grade"], "subject": task["subject"],
            "outcome_id": task.get("outcome_id"), "split": task.get("split"), "requested_model": MODEL,
            "pricing_snapshot": PRICING_SNAPSHOT, "run_date": datetime.now(timezone.utc).date().isoformat()}
    allowed: list[str] = []
    retrieval_s = 0.0
    if condition == "B":
        if bundle is None:
            raise ValueError("condition B needs an evidence bundle")
        bundle.verify()
        retrieval_s = bundle.retrieval_latency_s
        base.update(bundle_hash=bundle.bundle_hash, chunk_ids=bundle.chunk_ids, corpus_hash=bundle.corpus_hash)
        if bundle.status != "ok":
            result = dict(base, status=bundle.status, job_status=bundle.status, reason=bundle.reason,
                          displayed_message=bundle.displayed_message, attempts=0, output=None, output_candidate=None,
                          generation_called=False, completion=0, word_count=0, prompt_tokens=0, completion_tokens=0,
                          cached_tokens=0, gen_latency_s=0.0, retrieval_latency_s=retrieval_s, cost_usd=0.0,
                          total_latency_s=round(time.perf_counter() - t_job + retrieval_s, 3), event="result", ts=_now())
            logger.log(result)
            return result
        allowed = bundle.chunk_ids
    g = generate_validated(client, logger, base, build_messages(task, condition, bundle),
                           lambda raw: parse_and_check(raw, condition, task["grade"], task["subject"], allowed),
                           max_tokens, retry_delay_s)
    out = g["parsed"].model_dump() if g["parsed"] is not None else None
    status = g["status"]
    if status == "ok" and out["status"] == "insufficient_evidence":
        status = "insufficient_evidence"  # model-declared gap (not a gate refusal)
    result = dict(base, status=status, job_status=status, reason=g["error"] or (out or {}).get("reason", ""),
                  displayed_message="", attempts=g["attempts"], api_failures=g["api_failures"], output=out,
                  output_candidate=None if out else g["candidate"], generation_called=True,
                  completion=1 if status == "ok" else 0, word_count=word_count(out or g["candidate"]),
                  prompt_tokens=g["prompt_tokens"], completion_tokens=g["completion_tokens"], cached_tokens=g["cached_tokens"],
                  gen_latency_s=g["gen_latency_s"], retrieval_latency_s=retrieval_s, cost_usd=g["cost_usd"],
                  total_latency_s=round(time.perf_counter() - t_job + retrieval_s, 3), event="result", ts=_now())
    logger.log(result)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
