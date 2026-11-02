"""Conditions A (no retrieval) and B (frozen evidence bundle with chunk-ID citations). Doc 3 T2/T4.

Rules implemented:
- B never calls the model when the coverage gate failed; it returns insufficient_evidence directly (TEST 001).
- The bundle hash is verified before generation; a mismatch stops the run.
- Invalid JSON / schema / citation -> one regeneration; both attempts are counted and logged.
- API timeout -> one bounded retry, then status "incomplete" with the trace kept.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .llm import MAX_TOKENS_AB, LLMClient, LLMTimeout, cost_usd, is_peak
from .retrieval import EvidenceBundle
from .schema import OutputError, parse_and_check

SCHEMA_HINT = """Return ONLY a JSON object with these keys:
{"status": "ok" | "insufficient_evidence", "grade": int, "subject": "maths"|"science", "outcome_id": str|null,
 "title": str, "objectives": [{"text": str, "citations": [chunk_id]}],
 "activities": [{"step": int, "description": str, "minutes": int, "citations": [chunk_id]}],
 "differentiation": {"support": str, "extension": str},
 "assessment": [{"text": str, "citations": [chunk_id]}], "feedback": str, "reason": str}
Target 700-900 words of content in total."""

SYSTEM_A = ("You are a lesson-planning assistant for UAE Ministry of Education Cycle 1 teachers. "
            "Write in English. No curriculum evidence is supplied; use your general knowledge and leave every "
            "citations list empty. " + SCHEMA_HINT)

SYSTEM_B = ("You are a lesson-planning assistant for UAE Ministry of Education Cycle 1 teachers. Write in English. "
            "Use ONLY the curriculum evidence chunks supplied. Every objective, activity and assessment item must cite "
            "one or more chunk IDs exactly as given (e.g. \"moe-ma-g3-004\"). Never invent IDs. If the evidence does not "
            "cover the requested outcome, return status \"insufficient_evidence\" with a reason and empty lists. " + SCHEMA_HINT)


def task_prompt(task: dict) -> str:
    return (f"Task {task['task_id']}: Grade {task['grade']} {task['subject']}. Outcome: {task.get('outcome_id') or 'n/a'}. "
            f"Topic: {task['topic']}. Class context: {task.get('context', 'mixed-ability class of 25, 45-minute lesson')}. "
            "Produce a lesson plan with differentiation, assessment and feedback.")


def evidence_block(b: EvidenceBundle) -> str:
    return "\n\n".join(f"<chunk id=\"{c['chunk_id']}\">\n{c['text']}\n</chunk>" for c in b.chunks)


def build_messages(task: dict, condition: str, bundle: EvidenceBundle | None) -> list[dict]:
    if condition == "A":
        return [{"role": "system", "content": SYSTEM_A}, {"role": "user", "content": task_prompt(task)}]
    return [{"role": "system", "content": SYSTEM_B},
            {"role": "user", "content": f"EVIDENCE (bundle {bundle.bundle_hash[:12]}):\n{evidence_block(bundle)}\n\n{task_prompt(task)}"}]


class TraceLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, rec: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_condition(task: dict, condition: str, client: LLMClient, logger: TraceLogger,
                  bundle: EvidenceBundle | None = None, repeat: int = 1, max_tokens: int = MAX_TOKENS_AB) -> dict:
    if condition not in ("A", "B"):
        raise ValueError("this module implements conditions A and B only")
    run_id = uuid.uuid4().hex[:12]
    base = {"run_id": run_id, "task_id": task["task_id"], "condition": condition, "repeat": repeat,
            "grade": task["grade"], "subject": task["subject"]}
    allowed: list[str] = []
    if condition == "B":
        if bundle is None:
            raise ValueError("condition B needs an evidence bundle")
        bundle.verify()
        base.update(bundle_hash=bundle.bundle_hash, chunk_ids=bundle.chunk_ids, corpus_hash=bundle.corpus_hash)
        if bundle.status != "ok":
            result = dict(base, status="insufficient_evidence", reason=bundle.reason, attempts=0, output=None,
                          generation_called=False, total_prompt_tokens=0, total_completion_tokens=0, total_latency_s=0.0)
            logger.log(dict(result, event="gate_refusal", ts=_now()))
            return result
        allowed = bundle.chunk_ids
    messages = build_messages(task, condition, bundle)
    attempts, timeouts, tok_in, tok_out, lat, cost = 0, 0, 0, 0, 0.0, 0.0
    last_err, status, output = "", "invalid_output", None
    format_retry_used = False
    while True:
        attempts += 1
        t = datetime.now(timezone.utc)
        try:
            r = client.complete(messages, max_tokens)
        except LLMTimeout as e:
            timeouts += 1
            logger.log(dict(base, event="timeout", attempt=attempts, error=str(e), ts=_now()))
            if timeouts > 1:
                status, last_err = "incomplete", "API timeout after one bounded retry"
                break
            continue
        tok_in += r.prompt_tokens; tok_out += r.completion_tokens; lat += r.latency_s
        c = cost_usd(r, is_peak(t.hour, t.weekday())); cost += c
        rec = dict(base, event="attempt", attempt=attempts, messages=messages, raw_output=r.text, model=r.model,
                   prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens, cached_tokens=r.cached_tokens,
                   latency_s=r.latency_s, finish_reason=r.finish_reason, cost_usd=round(c, 6), ts=_now())
        try:
            out = parse_and_check(r.text, condition, task["grade"], task["subject"], allowed)
            output, status, last_err = out.model_dump(), out.status, ""
            logger.log(dict(rec, valid=True))
            break
        except OutputError as e:
            last_err = str(e)
            logger.log(dict(rec, valid=False, error=last_err))
            if format_retry_used:
                break
            format_retry_used = True
            messages = messages + [{"role": "assistant", "content": r.text},
                                   {"role": "user", "content": f"Your output was rejected: {last_err}. Return corrected JSON only."}]
    result = dict(base, status=status, reason=last_err, attempts=attempts, output=output, generation_called=True,
                  total_prompt_tokens=tok_in, total_completion_tokens=tok_out, total_latency_s=round(lat, 3),
                  total_cost_usd=round(cost, 6))
    logger.log(dict(result, event="result", ts=_now()))
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
