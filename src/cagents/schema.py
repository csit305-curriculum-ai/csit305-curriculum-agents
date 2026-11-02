"""Teaching-pack schema shared by conditions A, B and C (Doc 3: four sections, objective IDs link sections).

Sections: planning (objectives + lesson sequence), differentiation (support + extension),
assessment (questions with answer keys), feedback (templates for answer patterns).
Section models are exported so condition C specialists can validate their own section.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

SECTIONS = ("planning", "differentiation", "assessment", "feedback")


class Cited(BaseModel):
    citations: list[str] = Field(default_factory=list)


class Objective(Cited):
    objective_id: str = Field(pattern=r"^O\d+$")
    text: str = Field(min_length=5)


class Linked(Cited):
    objective_ids: list[str] = Field(min_length=1)


class Step(Linked):
    step: int = Field(ge=1)
    description: str = Field(min_length=5)
    minutes: int = Field(ge=1, le=120)


class Planning(BaseModel):
    objectives: list[Objective] = Field(min_length=1)
    lesson_sequence: list[Step] = Field(min_length=1)


class Activity(Linked):
    description: str = Field(min_length=5)


class Differentiation(BaseModel):
    support: list[Activity] = Field(min_length=1)
    extension: list[Activity] = Field(min_length=1)


class Question(Linked):
    question_id: str = Field(pattern=r"^Q\d+$")
    question: str = Field(min_length=5)
    answer_key: str = Field(min_length=1)


class Assessment(BaseModel):
    questions: list[Question] = Field(min_length=1)


class FeedbackTemplate(Linked):
    answer_pattern: str = Field(min_length=3)
    feedback: str = Field(min_length=5)


class Feedback(BaseModel):
    templates: list[FeedbackTemplate] = Field(min_length=1)


SECTION_MODELS = {"planning": Planning, "differentiation": Differentiation, "assessment": Assessment, "feedback": Feedback}


class TeachingPack(BaseModel):
    status: Literal["ok", "insufficient_evidence"]
    grade: int = Field(ge=1, le=4)
    subject: Literal["maths", "science"]
    outcome_id: str | None = None
    title: str = ""
    planning: Planning | None = None
    differentiation: Differentiation | None = None
    assessment: Assessment | None = None
    feedback: Feedback | None = None
    reason: str = ""

    @model_validator(mode="after")
    def _shape(self) -> "TeachingPack":
        if self.status == "ok":
            missing = [s for s in SECTIONS if getattr(self, s) is None]
            if missing:
                raise ValueError(f"status ok requires all four sections; missing {missing}")
            ids = {o.objective_id for o in self.planning.objectives}
            bad = sorted({oid for it in linked_items(self) for oid in it.objective_ids} - ids)
            if bad:
                raise ValueError(f"objective_ids not defined in planning.objectives: {bad}")
        elif not self.reason:
            raise ValueError("insufficient_evidence requires a reason")
        return self


def linked_items(p: TeachingPack) -> list[Linked]:
    return (list(p.planning.lesson_sequence) + list(p.differentiation.support) + list(p.differentiation.extension)
            + list(p.assessment.questions) + list(p.feedback.templates))


def cited_items(p: TeachingPack) -> list[tuple[str, str, BaseModel]]:
    """(section, item_ref, item) for every citable item, in a fixed order."""
    if p.status != "ok":
        return []
    out = [("planning", o.objective_id, o) for o in p.planning.objectives]
    out += [("planning", f"step{s.step}", s) for s in p.planning.lesson_sequence]
    out += [("differentiation", f"support{i+1}", a) for i, a in enumerate(p.differentiation.support)]
    out += [("differentiation", f"extension{i+1}", a) for i, a in enumerate(p.differentiation.extension)]
    out += [("assessment", q.question_id, q) for q in p.assessment.questions]
    out += [("feedback", f"template{i+1}", t) for i, t in enumerate(p.feedback.templates)]
    return out


def item_text(item: BaseModel) -> str:
    for f in ("text", "description", "question", "feedback"):
        if hasattr(item, f):
            extra = f" Answer: {item.answer_key}" if hasattr(item, "answer_key") else ""
            return getattr(item, f) + extra
    return ""


def word_count(p: TeachingPack | dict | None) -> int:
    if p is None:
        return 0
    d = p.model_dump() if isinstance(p, BaseModel) else p
    skip = {"citations", "objective_ids", "objective_id", "question_id", "status", "outcome_id", "grade", "subject", "step", "minutes"}

    def walk(x, key=None):
        if key in skip:
            return 0
        if isinstance(x, str):
            return len(re.findall(r"\S+", x))
        if isinstance(x, dict):
            return sum(walk(v, k) for k, v in x.items())
        if isinstance(x, list):
            return sum(walk(v) for v in x)
        return 0
    return walk(d)


class OutputError(ValueError):
    pass


def check_citations(cites: list[str], condition: str, allowed_ids: list[str], status: str) -> None:
    if condition == "A" and cites:
        raise OutputError("condition A has no evidence, so it must not cite chunk IDs")
    if condition in ("B", "C"):
        bad = sorted(set(cites) - set(allowed_ids))
        if bad:
            raise OutputError(f"invalid citation IDs not in evidence bundle: {bad}")
        if status == "ok" and not cites:
            raise OutputError(f"condition {condition} output must cite evidence chunk IDs")


def parse_and_check(raw: str, condition: str, grade: int, subject: str, allowed_ids: list[str]) -> TeachingPack:
    """Raise OutputError on malformed JSON, schema failure, grade/subject change, or invalid citations."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OutputError(f"malformed JSON: {e.msg}") from e
    try:
        out = TeachingPack.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        raise OutputError(f"schema: {'.'.join(map(str, err['loc']))} {err['msg']}") from e
    if out.grade != grade or out.subject != subject:
        raise OutputError(f"grade/subject changed: got {out.grade}/{out.subject}, task {grade}/{subject}")
    check_citations([c for _, _, it in cited_items(out) for c in it.citations], condition, allowed_ids, out.status)
    return out


def parse_section(raw: str, section: str, condition: str, allowed_ids: list[str], objective_ids: set[str] | None = None) -> BaseModel:
    """For condition C specialists: validate one section with the same citation rules."""
    try:
        data = json.loads(raw)
        sec = SECTION_MODELS[section].model_validate(data.get(section, data))
    except json.JSONDecodeError as e:
        raise OutputError(f"malformed JSON: {e.msg}") from e
    except ValidationError as e:
        err = e.errors()[0]
        raise OutputError(f"schema: {section}.{'.'.join(map(str, err['loc']))} {err['msg']}") from e
    def walk(x):
        if isinstance(x, Cited):
            yield x
        if isinstance(x, BaseModel):
            for v in x.__dict__.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)
    items = list(walk(sec))
    check_citations([c for it in items for c in it.citations], condition, allowed_ids, "ok")
    if objective_ids is not None:
        bad = sorted({o for it in items if isinstance(it, Linked) for o in it.objective_ids} - objective_ids)
        if bad:
            raise OutputError(f"objective_ids not defined in planning: {bad}")
    return sec
