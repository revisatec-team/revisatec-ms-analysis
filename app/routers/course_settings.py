"""Routers for course settings: rubric, instructions, scraping-config."""
from fastapi import APIRouter, Path
from app.models.course_settings import Rubric, Instructions, ScrapingConfig
from app.services import course_settings as service

router = APIRouter(prefix="/courses/{id}", tags=["Course configuration"])


@router.get("/rubric", response_model=Rubric, operation_id="getRubric")
def get_rubric(id: int = Path(..., description="ID del curso")):
    """Obtener rúbrica del curso."""
    return service.get_rubric(course_id=id)


@router.put("/rubric", response_model=Rubric, operation_id="updateRubric")
def update_rubric(rubric: Rubric, id: int = Path(..., description="ID del curso")):
    """Reemplazar o crear rúbrica del curso."""
    return service.update_rubric(course_id=id, rubric_input=rubric)


@router.get("/instructions", response_model=Instructions, operation_id="getInstructions")
def get_instructions(id: int = Path(..., description="ID del curso")):
    """Obtener indicaciones para la IA."""
    return service.get_instructions(course_id=id)


@router.put("/instructions", response_model=Instructions, operation_id="updateInstructions")
def update_instructions(instructions: Instructions, id: int = Path(..., description="ID del curso")):
    """Actualizar indicaciones para la IA."""
    return service.update_instructions(course_id=id, instructions_input=instructions)


@router.get("/scraping-config", response_model=ScrapingConfig, operation_id="getScrapingConfig")
def get_scraping_config(id: int = Path(..., description="ID del curso")):
    """Obtener configuración de scraping."""
    return service.get_scraping_config(course_id=id)


@router.put("/scraping-config", response_model=ScrapingConfig, operation_id="updateScrapingConfig")
def update_scraping_config(config: ScrapingConfig, id: int = Path(..., description="ID del curso")):
    """Actualizar configuración de scraping."""
    return service.update_scraping_config(course_id=id, config_input=config)
