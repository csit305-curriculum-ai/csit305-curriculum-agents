"""Condition C: four specialist calls in a fixed order, plain-Python orchestration (Doc 3 T2/T4, docs/CONDITION_C_PLAN.md).

AI-written (Grok Bot) at Sanjay's request, 2 Nov 2026; pending review and ownership by Manzi (see AI_USE.md).

Rules (DEC 017-021):
- Nodes run in order planning -> differentiation -> assessment -> feedback. No LangGraph; a for-loop.
- Every node receives the SAME frozen evidence packet as B plus the earlier validated drafts it depends on.
- Coverage gate before any call: if the packet is not "ok", no model call is made and the job refuses.
- Each node uses conditions.generate_validated (same model settings, one regeneration, one bounded retry).
- 800 output tokens per specialist (MAX_TOKENS_C_NODE).
- Python assembles the TeachingPack; there is NO fifth model call.
- A failed node stops the job (job_status incomplete, failed_node set). B is never substituted.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from .conditions import TraceLogger, evidence_block, generate_validated, task_prompt
from .llm import MODEL, PRICING_SNAPSHOT, LLMClient
from .retrieval import EvidenceBundle
from .schema import OutputError, TeachingPack, parse_section, word_count

NODES = ("planning", "differentiation", "assessment", "feedback")
MAX_TOKENS_C_NODE = 800
UPSTREAM = {"planning": (), "differentiation": ("planning",), "assessment": ("planning",),
            "feedback": ("planning", "assessment")}

SECTION_HINT = {
    "planning": '{"planning": {"objectives": [{"objective_id": "O1", "text": str, "citations": [chunk_id]}], '
                '"lesson_sequence": [{"step": 1, "description": str, "minutes": int, "objective_ids": ["O1"], "citations": [chunk_id]}]}}',
    "differentiation": '{"differentiation": {"support": [{"description": str, "objective_ids": ["O1"], "citations": [chunk_id]}], '
                       '"extension": [{"description": str, "objective_ids": ["O1"], "citations": [chunk_id]}]}}',
    "assessment": '{"assessment": {"questions": [{"question_id": "Q1", "question": str, "answer_key": str, '
                  '"objective_ids": ["O1"], "citations": [chunk_id]}]}}',
    "feedback": '{"feedback": {"templates": [{"answer_pattern": str, "feedback": str, "objective_ids": ["O1"], '
                '"citations": [chunk_id]}]}}',
}
ROLE = {
    "planning": "the PLANNING specialist: write learning objectives (O1, O2, ...) and a timed lesson sequence",
    "differentiation": "the DIFFERENTIATION specialist: write support and extension activities for the planned objectives",
    "assessment": "the ASSESSMENT specialist: write questions (Q1, Q2, ...) with answer keys for the planned objectives",
    "feedback": "the FEEDBACK specialist: write feedback templates for likely answer patterns to the assessment questions "
                "(never identifiable pupils)",
}


def system_prompt(node: str) -> str:
    return (f"You are {ROLE[node]} in a four-agent team preparing a teaching pack for UAE Ministry of Education Cycle 1 "
            "teachers. Write in English. Use ONLY the curriculum evidence passages supplied and cite passage IDs exactly as "
            "given; never invent IDs. Only link objective IDs defined by the planning specialist. "
            f"Return ONLY one JSON object: {SECTION_HINT[node]}. Keep your section under about 250 words.")


def node_messages(node: str, task: dict, bundle: EvidenceBundle, upstream: dict[str, dict]) -> list[dict]:
    parts = [f"EVIDENCE PACKET {bundle.bundle_hash[:12]}:\n{evidence_block(bundle)}", task_prompt(task)]
    for u in UPSTREAM[node]:
        parts.append(f"EARLIER DRAFT ({u}, already validated):\n" + json.dumps({u: upstream[u]}, ensure_ascii=False))
    parts.append(f"Write only the {node} section.")
    return [{"role": "system", "content": system_prompt(node)}, {"role": "user", "content": "\n\n".join(parts)}]


def run_node(node: str, task: dict, bundle: EvidenceBundle, upstream: dict[str, dict], client: LLMClient,
             logger: TraceLogger, base: dict, retry_delay_s: float | None = None) -> dict:
    objective_ids = None if node == "planning" else {o["objective_id"] for o in upstream["planning"]["objectives"]}
    qids = {q["question_id"] for q in upstream.get("assessment", {}).get("questions", [])}

    def validate(raw: str):
        sec = parse_section(raw, node, "C", bundle.chunk_ids, objective_ids)
        if node == "planning":
            ids = [o.objective_id for o in sec.objectives]
            if len(ids) != len(set(ids)):
                raise OutputError("duplicate objective_id in planning")
            bad = sorted({o for s in sec.lesson_sequence for o in s.objective_ids} - set(ids))
            if bad:
                raise OutputError(f"objective_ids not defined in planning: {bad}")
        if node == "assessment":
            ids = [q.question_id for q in sec.questions]
            if len(ids) != len(set(ids)):
                raise OutputError("duplicate question_id in assessment")
        return sec

    nb = dict(base, node=node, node_pos=NODES.index(node) + 1)
    g = generate_validated(client, logger, nb, node_messages(node, task, bundle, upstream), validate,
                           MAX_TOKENS_C_NODE, retry_delay_s)
    section = g["parsed"].model_dump() if g["parsed"] is not None else None
    rec = dict(nb, event="node_result", status=g["status"], error=g["error"], attempts=g["attempts"],
               api_failures=g["api_failures"], prompt_tokens=g["prompt_tokens"], completion_tokens=g["completion_tokens"],
               cached_tokens=g["cached_tokens"], gen_latency_s=g["gen_latency_s"], cost_usd=g["cost_usd"],
               valid=section is not None, section=section, ts=_now())
    logger.log(rec)
    return dict(rec, _qids=qids)


def assemble(task: dict, sections: dict[str, dict], bundle: EvidenceBundle) -> TeachingPack:
    """Pure Python assembly into the shared TeachingPack (no model call). Re-validates cross-section links."""
    return TeachingPack.model_validate({"status": "ok", "grade": task["grade"], "subject": task["subject"],
                                        "outcome_id": task.get("outcome_id"), "title": task["topic"], **sections, "reason": ""})


def run_condition_c(task: dict, client: LLMClient, logger: TraceLogger, bundle: EvidenceBundle, repeat: int = 1,
                    job_id: str | None = None, order_pos: int | None = None, retry_delay_s: float | None = None) -> dict:
    if bundle is None:
        raise ValueError("condition C needs the frozen evidence bundle")
    t_job = time.perf_counter()
    run_id = uuid.uuid4().hex[:12]
    bundle.verify()
    base = {"run_id": run_id, "job_id": job_id or run_id, "task_id": task["task_id"], "condition": "C", "repeat": repeat,
            "order_pos": order_pos, "grade": task["grade"], "subject": task["subject"], "outcome_id": task.get("outcome_id"),
            "split": task.get("split"), "requested_model": MODEL, "pricing_snapshot": PRICING_SNAPSHOT,
            "run_date": datetime.now(timezone.utc).date().isoformat(), "bundle_hash": bundle.bundle_hash,
            "chunk_ids": bundle.chunk_ids, "corpus_hash": bundle.corpus_hash}
    zero = dict(prompt_tokens=0, completion_tokens=0, cached_tokens=0, gen_latency_s=0.0, cost_usd=0.0)
    if bundle.status != "ok":  # coverage gate: refuse before any model call
        res = dict(base, node="job", event="result", status=bundle.status, job_status=bundle.status, failed_node=None,
                   reason=bundle.reason, displayed_message=bundle.displayed_message, attempts=0, api_failures=0,
                   nodes=[], output=None, output_candidate=None, generation_called=False, model_calls=0, completion=0,
                   word_count=0, retrieval_latency_s=bundle.retrieval_latency_s,
                   total_latency_s=round(time.perf_counter() - t_job + bundle.retrieval_latency_s, 3), ts=_now(), **zero)
        logger.log(res)
        return res
    sections: dict[str, dict] = {}
    nodes: list[dict] = []
    failed, status, reason = None, "ok", ""
    for node in NODES:
        r = run_node(node, task, bundle, sections, client, logger, base, retry_delay_s)
        r.pop("_qids", None)
        nodes.append(r)
        if r["section"] is None:
            failed, status, reason = node, r["status"] if r["status"] != "ok" else "invalid_output", r["error"]
            break
        sections[node] = r["section"]
    out = None
    if failed is None:
        try:
            out = assemble(task, sections, bundle).model_dump()
        except Exception as e:  # cross-section link failure
            status, reason, failed = "invalid_output", f"assembly: {e}", "assembly"
    tot = {k: sum(n[k] for n in nodes) for k in ("prompt_tokens", "completion_tokens", "cached_tokens", "attempts", "api_failures")}
    gen_lat = round(sum(n["gen_latency_s"] for n in nodes), 3)
    cost = round(sum(n["cost_usd"] for n in nodes), 6)
    job_status = "ok" if out else "incomplete"
    res = dict(base, node="job", event="result", status=status if out is None else "ok", job_status=job_status,
               failed_node=failed, reason=reason, displayed_message="", nodes=[
                   {k: n[k] for k in ("node", "node_pos", "status", "attempts", "prompt_tokens", "completion_tokens",
                                      "gen_latency_s", "cost_usd", "error")} for n in nodes],
               output=out, output_candidate=None if out else sections or None, generation_called=True,
               model_calls=tot["attempts"], completion=1 if out else 0, word_count=word_count(out) if out else 0,
               gen_latency_s=gen_lat, cost_usd=cost, retrieval_latency_s=bundle.retrieval_latency_s,
               total_latency_s=round(time.perf_counter() - t_job + bundle.retrieval_latency_s, 3), ts=_now(), **tot)
    logger.log(res)
    return res


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
