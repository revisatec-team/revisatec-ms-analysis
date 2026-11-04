"""Pydantic models for course settings: rubric, instructions, and scraping-config."""
import math
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ScrapingFrequency(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class Criterion(BaseModel):
    name: str = Field(..., min_length=1, description="Nombre del criterio")
    weight: float = Field(..., description="Peso del criterio (0 a 100)")

    @field_validator("weight")
    @classmethod
    def validate_weight_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("El peso de cada criterio debe estar entre 0 y 100")
        return v


class Rubric(BaseModel):
    criteria: List[Criterion] = Field(..., description="Criterios de evaluación")
    fileName: Optional[str] = Field(None, description="Archivo de rúbrica interpretado (solo lectura)")
    interpretationStatus: Optional[str] = Field(None, description="Texto del estado de interpretación por IA (solo lectura)")

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, v: List[Criterion]) -> List[Criterion]:
        if not v or len(v) == 0:
            raise ValueError("La lista de criterios no puede estar vacía")
        total_weight = sum(c.weight for c in v)
        if not math.isclose(total_weight, 100.0, abs_tol=1e-5):
            raise ValueError("Los pesos de la rúbrica deben sumar 100")
        return v


class Instructions(BaseModel):
    text: str = Field(..., max_length=1000, description="Indicaciones para la IA")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if len(v) > 1000:
            raise ValueError("Las indicaciones no pueden superar los 1000 caracteres")
        return v


class ScrapingConfig(BaseModel):
    frequency: ScrapingFrequency = Field(..., description="Frecuencia de scraping (hourly|daily|weekly)")
    minReviewers: int = Field(..., ge=1, description="Mínimo de revisores por pull request")
    nextRunAt: Optional[int] = Field(None, description="Próximo análisis en Epoch ms")

    @field_validator("minReviewers")
    @classmethod
    def validate_min_reviewers(cls, v: int) -> int:
        if v < 1:
            raise ValueError("minReviewers debe ser al menos 1")
        return v


class CourseSettingsDocument(BaseModel):
    courseId: int
    rubric: Optional[Rubric] = None
    instructions: Optional[Instructions] = None
    scrapingConfig: Optional[ScrapingConfig] = None
