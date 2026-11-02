"""LLM client interface. DeepSeekClient is the real one; MockClient is used by all tests."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

MODEL = "deepseek-flash"
TEMPERATURE = 0.3
MAX_TOKENS_AB = 2400
TIMEOUT_S = 120
# USD per 1M tokens, deepseek-flash, from api-docs.deepseek.com/quick_start/pricing (read 2 Nov 2026).
PRICE = {"peak": {"in_miss": 0.30, "in_hit": 0.006, "out": 1.20}, "offpeak": {"in_miss": 0.15, "in_hit": 0.003, "out": 0.60}}


class LLMTimeout(Exception):
    pass


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    model: str
    cached_tokens: int = 0
    finish_reason: str = ""


class LLMClient(Protocol):
    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse: ...


def is_peak(utc_hour: int, weekday: int) -> bool:
    return weekday < 5 and (1 <= utc_hour < 4 or 6 <= utc_hour < 10)


def cost_usd(r: LLMResponse, peak: bool) -> float:
    p = PRICE["peak" if peak else "offpeak"]
    miss = r.prompt_tokens - r.cached_tokens
    return (miss * p["in_miss"] + r.cached_tokens * p["in_hit"] + r.completion_tokens * p["out"]) / 1e6


class DeepSeekClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str = MODEL) -> None:
        from openai import OpenAI
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        self.model = model
        self.client = OpenAI(api_key=key, base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                             timeout=TIMEOUT_S, max_retries=0)  # retries are handled (and counted) by the pipeline

    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse:
        import openai
        t0 = time.perf_counter()
        try:
            r = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=TEMPERATURE, max_tokens=max_tokens,
                response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}})
        except openai.APITimeoutError as e:
            raise LLMTimeout(str(e)) from e
        u = r.usage
        cached = getattr(u, "prompt_cache_hit_tokens", None) or 0
        return LLMResponse(text=r.choices[0].message.content or "", prompt_tokens=u.prompt_tokens,
                           completion_tokens=u.completion_tokens, latency_s=round(time.perf_counter() - t0, 3),
                           model=r.model, cached_tokens=cached, finish_reason=r.choices[0].finish_reason or "")


class MockClient:
    """Returns scripted outputs in order. An item that is an Exception instance is raised instead."""

    def __init__(self, outputs: list) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        if not self.outputs:
            raise AssertionError("MockClient ran out of scripted outputs")
        item = self.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, prompt_tokens=sum(len(m["content"]) // 4 for m in messages),
                           completion_tokens=len(item) // 4, latency_s=0.01, model="mock")
