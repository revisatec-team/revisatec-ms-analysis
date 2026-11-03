"""Common models and pagination schemas for MS2 Analysis."""
from typing import Generic, List, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "revisatec-ms-analysis"
    timestamp: int


class PaginatedResponse(BaseModel, Generic[T]):
    totalRecords: int
    page: int
    pageSize: int
    items: List[T]
