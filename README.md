# RevisaTEC MS2 - Rúbrica, IA y Análisis (`revisatec-ms-analysis`)

Microservicio de análisis de código, rúbricas, retroalimentación e inconvenientes para la plataforma **RevisaTEC**. Desarrollado con **Python 3.12**, **FastAPI** y **Azure Cosmos DB** (API para MongoDB), con integración asíncrona hacia **Azure Storage Queue** para notificaciones (MS3).

---

## 1. Arquitectura y Modelo de Datos

El microservicio utiliza Azure Cosmos DB (API para MongoDB) para almacenar configuraciones y eventos de manera documental:

- **`course_settings`**: Configuración unificada por curso (`courseId` único). Almacena `rubric` (criterios y pesos), `instructions` (indicaciones para el análisis) y `scrapingConfig` (frecuencia y revisores mínimos).
- **`github_events`**: Historial de commits y pull requests de cada grupo (`groupId`, `createdAt`).
- **`feedback`**: Propuesta de retroalimentación generada por reglas e versión editada/publicada por el profesor (`groupId` único).
- **`issues`**: Inconvenientes detectados automáticamente en commits (`groupId`, `date`, `sourceEventId`).
- **`direct_reviews`**: Revisiones directas registradas fuera del flujo habitual (`groupId`, `date`).
- **`report_checklist`**: Hitos y entregas programadas por grupo (`groupId`).

> **Reglas del Análisis**: El análisis (`/groups/{id}/analysis`, `/progress-summary`, `/criteria`) se calcula dinámicamente al vuelo a partir de `github_events` y la rúbrica del curso; no se almacena en una colección separada.

---

## 2. Variables de Entorno

Crear un archivo `.env` en la raíz a partir de `.env.example`:

```bash
cp .env.example .env
```

| Variable | Descripción | Valor por Defecto / Ejemplo |
|---|---|---|
| `COSMOS_CONNECTION_STRING` | Cadena de conexión de Azure Cosmos DB (API Mongo) | `mongodb://localhost:27017` |
| `COSMOS_DB_NAME` | Nombre de la base de datos documental | `revisatec` |
| `QUEUE_CONNECTION_STRING` | Cadena de conexión de Azure Storage Queue | `DefaultEndpointsProtocol=https;AccountName=...` |
| `QUEUE_NAME` | Nombre de la cola de notificaciones | `notificaciones` |
| `PORT` | Puerto de escucha del servicio | `8000` |

---

## 3. Instalación y Ejecución Local

### Prerrequisitos
- Python 3.12+
- Servidor MongoDB o Azure Cosmos DB

### Pasos

1. **Crear y activar entorno virtual**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Cargar datos iniciales (Seed idempotente)**:
   ```bash
   python scripts/seed.py
   ```

4. **Iniciar el servidor de desarrollo**:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

La documentación Swagger interactiva queda disponible en `http://localhost:8000/docs`.

---

## 4. Tabla de Endpoints

Todos los errores retornan el formato `{ "error": "mensaje" }`. Todas las fechas se intercambian en Epoch (milisegundos). Las listas siguen la convención `{ totalRecords, page, pageSize, items }`.

| Método | Endpoint | Descripción | Respuesta Exitosa | Códigos de Error |
|---|---|---|---|---|
| `GET` | `/health` | Estado del microservicio | `200 OK` | - |
| `GET` | `/courses/{id}/rubric` | Obtener rúbrica del curso | `200 OK` | `404 Not Found` |
| `PUT` | `/courses/{id}/rubric` | Guardar o actualizar rúbrica (pesos deben sumar 100) | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `GET` | `/courses/{id}/instructions` | Obtener indicaciones para la IA | `200 OK` | `404 Not Found` |
| `PUT` | `/courses/{id}/instructions` | Actualizar indicaciones (máx. 1000 caracteres) | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `GET` | `/courses/{id}/scraping-config` | Obtener configuración de scraping | `200 OK` | `404 Not Found` |
| `PUT` | `/courses/{id}/scraping-config` | Actualizar scraping (recalcula `nextRunAt`) | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `GET` | `/groups/{id}/analysis` | Puntaje total, progreso, criterios y 10 evidencias recientes | `200 OK` | `404 Not Found` |
| `GET` | `/groups/{id}/progress-summary` | Síntesis de avance por criterio (`on_track`, `at_risk`, `delayed`) | `200 OK` | `404 Not Found` |
| `GET` | `/groups/{id}/criteria` | Nivel de cumplimiento (`met`, `partial`, `not_met`) y puntajes | `200 OK` | `404 Not Found` |
| `GET` | `/groups/{id}/issues` | Inconvenientes detectados (paginado: `page`, `pageSize`) | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `GET` | `/groups/{id}/feedback` | Retroalimentación (IA borrador o versión profesor) | `200 OK` | `404 Not Found` |
| `PUT` | `/groups/{id}/feedback` | Guardar edición del profesor | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `POST` | `/groups/{id}/feedback/publish` | Publicar retroalimentación y emitir evento a la cola | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `GET` | `/groups/{id}/direct-reviews` | Listar revisiones directas del grupo (paginado) | `200 OK` | `400 Bad Request`, `404 Not Found` |
| `POST` | `/groups/{id}/direct-reviews` | Registrar revisión directa | `201 Created` | `400 Bad Request`, `404 Not Found` |
| `GET` | `/groups/{id}/report` | Lista de hitos y estado del reporte del grupo | `200 OK` | `404 Not Found` |

---

## 5. Integración con Azure Storage Queue (MS3)

Al ocurrir eventos clave, el microservicio publica mensajes JSON plano (UTF-8, sin codificación base64) en la cola `notificaciones`:

### Estructura del Mensaje
```json
{
  "eventId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "type": "FEEDBACK_PUBLISHED",
  "courseId": 1,
  "groupId": 1,
  "title": "Retroalimentación publicada",
  "message": "Se publicó la retroalimentación de Grupo 1",
  "createdAt": 1793000000000,
  "source": "ms-analysis"
}
```

- **`FEEDBACK_PUBLISHED`**: Emitido cuando el profesor publica la retroalimentación (`POST /groups/{id}/feedback/publish`). Si la cola falla, la publicación se preserva en base de datos y la respuesta indica `notified: false`.
- **`ISSUE_DETECTED`**: Emitido cuando se detectan nuevos commits con palabras sueltas de prueba (`test`, `prueba`, `wip`, `asdf`, `tmp`).

### Script para Envío de Evento de Prueba
```bash
python scripts/send_test_event.py --type FEEDBACK_PUBLISHED --course-id 1 --group-id 1
```

---

## 6. Pruebas Automatizadas

La suite de pruebas utiliza `pytest` y `mongomock`:

```bash
pytest -v
```
