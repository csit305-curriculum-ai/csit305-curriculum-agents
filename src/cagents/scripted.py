"""Offline SCRIPTED specialist client for Condition C demos/tests (no network, no model).

AI-written (Grok Bot), 2 Nov 2026. It returns fixed template sections that cite the passage IDs found in the prompt.
Its text is NOT model output and must never be reported as a quality result; it only exercises the C pipeline
(order, handoffs, validation, logging, assembly). Token counts are character/4 estimates, cost is computed from them.
"""
from __future__ import annotations

import json
import re

from .llm import LLMResponse

_NODE = re.compile(r"You are the (\w+) specialist")
_IDS = re.compile(r'<passage id="([^"]+)"')
_TOPIC = re.compile(r"Topic: (.*?)\. Lesson duration")


def scripted_section(node: str, ids: list[str], topic: str) -> dict:
    c = ids[:2]
    if node == "PLANNING":
        return {"planning": {"objectives": [
            {"objective_id": "O1", "text": f"[scripted] Explain the key idea of: {topic}", "citations": c[:1]},
            {"objective_id": "O2", "text": f"[scripted] Apply {topic.lower()} to a short task", "citations": c}],
            "lesson_sequence": [
                {"step": 1, "description": "[scripted] Warm-up linked to prior learning", "minutes": 10, "objective_ids": ["O1"], "citations": c[:1]},
                {"step": 2, "description": "[scripted] Guided practice in pairs", "minutes": 20, "objective_ids": ["O1", "O2"], "citations": c},
                {"step": 3, "description": "[scripted] Exit task and review", "minutes": 15, "objective_ids": ["O2"], "citations": c[:1]}]}}
    if node == "DIFFERENTIATION":
        return {"differentiation": {
            "support": [{"description": "[scripted] Worked example with visual aid", "objective_ids": ["O1"], "citations": c[:1]}],
            "extension": [{"description": "[scripted] Open-ended challenge task", "objective_ids": ["O2"], "citations": c}]}}
    if node == "ASSESSMENT":
        return {"assessment": {"questions": [
            {"question_id": "Q1", "question": f"[scripted] Question on {topic}", "answer_key": "[scripted key]", "objective_ids": ["O1"], "citations": c[:1]},
            {"question_id": "Q2", "question": "[scripted] Application question", "answer_key": "[scripted key]", "objective_ids": ["O2"], "citations": c}]}}
    return {"feedback": {"templates": [
        {"answer_pattern": "Correct answer to Q1", "feedback": "[scripted] Praise and ask for a reason", "objective_ids": ["O1"], "citations": c[:1]},
        {"answer_pattern": "Partial answer to Q2", "feedback": "[scripted] Prompt the missing step", "objective_ids": ["O2"], "citations": c}]}}


class ScriptedSpecialistClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        sysm, user = messages[0]["content"], messages[1]["content"]
        node = _NODE.search(sysm).group(1)
        topic = (_TOPIC.search(user) or [None, "the topic"])[1]
        text = json.dumps(scripted_section(node, _IDS.findall(user), topic))
        return LLMResponse(text=text, prompt_tokens=sum(len(m["content"]) // 4 for m in messages),
                           completion_tokens=len(text) // 4, latency_s=0.0, model="scripted-offline", finish_reason="stop")
