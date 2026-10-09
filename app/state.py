import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class Finding(BaseModel):
    category: str = Field(description="security | bug | style | tests")
    severity: str = Field(description="high | medium | low")
    file: str
    line: int | None = None
    message: str
    confidence: float = Field(default=0.7, ge=0, le=1)


class Findings(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class Verdict(BaseModel):
    valid: bool
    confidence: float = Field(ge=0, le=1)


class ReviewState(TypedDict, total=False):
    repo: str
    pr_number: int
    diff: str
    change_types: list[str]
    # reducer lets parallel reviewer nodes append to the same key
    findings: Annotated[list[Finding], operator.add]
    final_findings: list[Finding]
    pending: list[Finding]
    verify_attempts: int
    comment: str
    inline_comments: list[dict]
    posted: bool