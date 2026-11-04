"""Pydantic models for group reports."""
from typing import List
from pydantic import BaseModel


class ChecklistItem(BaseModel):
    name: str
    date: int   # Epoch ms
    status: str  # "completado" | "pendiente"


class Report(BaseModel):
    checklist: List[ChecklistItem]
