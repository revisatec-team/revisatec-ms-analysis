"""Pydantic models for feedback and direct reviews."""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class FeedbackInput(BaseModel):
    ai: Optional[str] = None
    professor: str = Field(..., description="Versión editable del profesor")

    @field_validator("professor")
    @classmethod
    def validate_professor(cls, v: str) -> str:
        if v is None:
            raise ValueError("El texto del profesor es obligatorio")
        return v


class Feedback(BaseModel):
    groupName: Optional[str] = None
    deliveryTitle: Optional[str] = None
    score: Optional[float] = None
    ai: Optional[str] = None
    professor: Optional[str] = None
    status: Optional[str] = Field("draft", description="draft | published")
    publishedAt: Optional[int] = None
    notified: Optional[bool] = None


class DirectReviewInput(BaseModel):
    note: str = Field(..., min_length=1, description="Nota de la revisión directa")

    @field_validator("note")
    @classmethod
    def validate_note(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La nota de revisión directa no puede estar vacía")
        return v.strip()


class DirectReview(DirectReviewInput):
    id: str
    date: int
