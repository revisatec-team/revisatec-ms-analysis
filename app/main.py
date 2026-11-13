"""Main application entry point for RevisaTEC MS2 Analysis."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db.cosmos import close_client, init_indexes
from app.routers import (
    health,
    course_settings,
    group_analysis,
    feedback,
    report,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: la app arranca aunque falle, pero el error queda en los logs
    try:
        init_indexes()
    except Exception:
        logger.exception("init_indexes falló al arrancar")
    yield
    # Shutdown logic
    close_client()


app = FastAPI(
    title="RevisaTEC - MS2 Rúbrica IA y reportes",
    description="Microservicio de Rúbrica, IA, análisis, retroalimentación e inconvenientes.",
    version="0.1.0",
    lifespan=lifespan,
)


# Global Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors and return HTTP 400 with {'error': 'mensaje'}."""
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        msg = first_error.get("msg", "Error de validación")
        loc_parts = [str(x) for x in first_error.get("loc", []) if x not in ("body",)]
        loc_str = " -> ".join(loc_parts)
        error_msg = f"{loc_str}: {msg}" if loc_str else msg
    else:
        error_msg = "Parámetros o cuerpo de la solicitud inválidos"
    return JSONResponse(status_code=400, content={"error": error_msg})


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Ensure all HTTPExceptions return {'error': 'mensaje'}."""
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Ensure Starlette HTTP exceptions (like default 404 or 405) return {'error': 'mensaje'}."""
    detail = exc.detail if exc.detail else "Error en la solicitud"
    if exc.status_code == 404 and detail == "Not Found":
        detail = "Recurso no encontrado"
    return JSONResponse(status_code=exc.status_code, content={"error": str(detail)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle unexpected server errors, log with path, and return HTTP 500."""
    logger.exception(f"Unhandled exception at {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})


# Routers
app.include_router(health.router)
app.include_router(course_settings.router)
app.include_router(group_analysis.router)
app.include_router(feedback.router)
app.include_router(report.router)
