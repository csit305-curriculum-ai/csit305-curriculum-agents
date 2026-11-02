"""Output JSON schema for conditions A and B, with citation checks against the evidence bundle."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


class Activity(BaseModel):
    step: int = Field(ge=1)
    description: str = Field(min_length=5)
    minutes: int = Field(ge=1, le=120)
    citations: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str = Field(min_length=5)
    citations: list[str] = Field(default_factory=list)


class LessonOutput(BaseModel):
    status: Literal["ok", "insufficient_evidence"]
    grade: int = Field(ge=1, le=4)
    subject: Literal["maths", "science"]
    outcome_id: str | None = None
    title: str = ""
    objectives: list[Claim] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    differentiation: dict[str, str] = Field(default_factory=dict)  # keys: support, extension
    assessment: list[Claim] = Field(default_factory=list)
    feedback: str = ""
    reason: str = ""  # required when status is insufficient_evidence

    @model_validator(mode="after")
    def _shape(self) -> "LessonOutput":
        if self.status == "ok":
            if not self.objectives or not self.activities or not self.assessment:
                raise ValueError("status ok requires objectives, activities and assessment")
            if not {"support", "extension"} <= set(self.differentiation):
                raise ValueError("differentiation needs 'support' and 'extension'")
        elif not self.reason:
            raise ValueError("insufficient_evidence requires a reason")
        return self

    def all_citations(self) -> list[str]:
        cites = [c for o in self.objectives for c in o.citations] + [c for a in self.activities for c in a.citations]
        return cites + [c for a in self.assessment for c in a.citations]


class OutputError(ValueError):
    pass


def parse_and_check(raw: str, condition: str, grade: int, subject: str, allowed_ids: list[str]) -> LessonOutput:
    """Raise OutputError with a short reason on malformed JSON, schema failure, or invalid citations."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OutputError(f"malformed JSON: {e.msg}") from e
    try:
        out = LessonOutput.model_validate(data)
    except ValidationError as e:
        raise OutputError(f"schema: {e.errors()[0]['loc']} {e.errors()[0]['msg']}") from e
    if out.grade != grade or out.subject != subject:
        raise OutputError(f"grade/subject mismatch: got {out.grade}/{out.subject}, task {grade}/{subject}")
    cites = out.all_citations()
    if condition == "A" and cites:
        raise OutputError("condition A has no evidence, so it must not cite chunk IDs")
    if condition == "B":
        bad = sorted(set(cites) - set(allowed_ids))
        if bad:
            raise OutputError(f"invalid citation IDs not in evidence bundle: {bad}")
        if out.status == "ok" and not cites:
            raise OutputError("condition B output must cite evidence chunk IDs")
    return out
