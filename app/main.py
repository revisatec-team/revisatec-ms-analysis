"""Main application entry point for RevisaTEC MS2 Analysis."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db.cosmos import close_client, init_indexes
from app.routers import health, course_settings, group_analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    try:
        init_indexes()
    except Exception:
        pass
    yield
    # Shutdown logic
    close_client()


app = FastAPI(
    title="RevisaTEC - MS2 Rúbrica IA y reportes",
    description="Microservicio de Rúbrica, IA, análisis, retroalimentación e inconvenientes.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Routers
app.include_router(health.router)
app.include_router(course_settings.router)
app.include_router(group_analysis.router)
