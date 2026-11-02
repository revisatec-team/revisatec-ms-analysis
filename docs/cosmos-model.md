# Modelo de datos de Cosmos DB (MS2: revisatec-ms-analysis)

Base de datos: `revisatec` (Azure Cosmos DB, API para MongoDB).
Convenciones: fechas en Epoch (milisegundos), identificadores de curso y grupo enteros (vienen de MS1), `id` de documentos propios como UUID sin guiones.

## Justificación

Los datos de MS2 son documentos con forma variable (rúbricas con criterios, eventos de repositorio, retroalimentación en texto, evidencia anidada) que se leen y escriben completos por curso o por grupo. Un almacén documental evita tablas intermedias y migraciones cuando cambia la rúbrica. MS1 usa SQL para datos relacionales (cursos, grupos, calendario) y MS3 usa cola e historial propio, de modo que los tres servicios usan almacenamientos distintos.

## Colecciones

### course_settings
Una por curso. Cubre rubric, instructions y scraping-config.

```json
{
  "courseId": 1,
  "rubric": {
    "fileName": "rubrica.pdf",
    "interpretationStatus": "Interpretada por IA",
    "criteria": [{ "name": "Calidad de código", "weight": 40 }]
  },
  "instructions": { "text": "Priorizar la revisión entre pares." },
  "scrapingConfig": { "frequency": "daily", "minReviewers": 1, "nextRunAt": 1793000000000 }
}
```
Índices: `courseId` (único).

### github_events
Eventos del repositorio de cada grupo (commits y pull requests).

```json
{
  "id": "a1b2c3",
  "groupId": 1,
  "type": "commit",
  "author": "estudiante1",
  "reviewers": [],
  "message": "feat: avance 3",
  "createdAt": 1793000000000
}
```
Índices: `groupId`, `createdAt`. Valores de `type`: `commit` o `pr`.

### feedback
Una por grupo: propuesta de IA y versión del profesor.

```json
{
  "groupId": 1,
  "courseId": 1,
  "deliveryTitle": null,
  "ai": "El grupo obtiene 72/100. ...",
  "professor": "",
  "status": "draft",
  "score": 72,
  "updatedAt": 1793000000000,
  "publishedAt": null
}
```
Índices: `groupId` (único). `status`: `draft` o `published`.

### issues
Inconvenientes detectados por las reglas.

```json
{
  "id": "d4e5f6",
  "groupId": 1,
  "type": "Commit de prueba",
  "description": "wip",
  "date": 1793000000000,
  "status": "Sin resolver",
  "sourceEventId": "a1b2c3"
}
```
Índices: `groupId`, `date`, `sourceEventId`. `status`: `Sin resolver` o `Resuelto`.

### direct_reviews
Revisiones directas con el profesor.

```json
{ "id": "g7h8i9", "groupId": 1, "date": 1793000000000, "note": "Se corrigió el PR #12." }
```
Índices: `groupId`, `date`.

### report_checklist
Hitos del reporte por grupo.

```json
{ "groupId": 1, "name": "Entrega 2: Prototipo", "date": 1793000000000, "status": "pendiente" }
```
Índices: `groupId`. `status`: `completado` o `pendiente`.

## Correspondencia con los endpoints de MS2

- `GET/PUT /courses/{id}/rubric`, `/instructions`, `/scraping-config`: `course_settings`.
- `GET /groups/{id}/analysis`, `/progress-summary`, `/criteria`: se calculan desde `github_events` y `course_settings` (no se guardan).
- `GET/PUT /groups/{id}/feedback` y `POST /groups/{id}/feedback/publish`: `feedback`.
- `GET /groups/{id}/issues`: `issues` (la detección lee `github_events`).
- `GET/POST /groups/{id}/direct-reviews`: `direct_reviews`.
- `GET /groups/{id}/report`: `report_checklist`.

## Pendientes por confirmar

- Si la cuenta de Cosmos es serverless o de throughput compartido, y si las colecciones requieren clave de partición.
- Si `GET /groups/{id}/members` (usado por el front) lo sirve MS1 o MS2.
