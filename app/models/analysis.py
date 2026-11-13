"""Pydantic models for group analysis, criteria compliance, progress summary, and issues."""
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class CriterionScore(BaseModel):
    name: str
    score: float
    max: float
    percent: int
    level: str  # "Bueno", "En progreso", "Bajo"
    type: str   # "success", "warning", "alert"


class Evidence(BaseModel):
    id: str
    type: str   # "commit", "pr"
    text: str
    author: str
    reviewer: Optional[str] = None
    when: int   # Epoch ms


class Analysis(BaseModel):
    score: float
    progress: int
    criteria: List[CriterionScore]
    evidence: List[Evidence]


class ProgressItem(BaseModel):
    criterionId: str
    name: str
    status: str  # "on_track", "at_risk", "delayed"
    note: str


class ProgressSummary(BaseModel):
    groupId: int
    overall: int
    items: List[ProgressItem]
    generatedAt: int


class CriterionCompliance(BaseModel):
    criterionId: str
    name: str
    level: str  # "not_met", "partial", "met"
    score: float


class GroupCriteriaResponse(BaseModel):
    groupId: int
    items: List[CriterionCompliance]


class Issue(BaseModel):
    id: Union[int, str]
    groupId: int
    groupName: str
    type: str
    description: str
    date: int
    status: str
