# Reglas de rúbrica y análisis (MS2: revisatec-ms-analysis)

El análisis es determinista y se calcula al consultarlo, a partir de los eventos guardados del repositorio y de la rúbrica del curso. No usa IA real; el texto de la propuesta se genera con plantillas.

## 1. Métricas del grupo (0 a 100)

- **Código:** `min(100, commits / 20 × 100)`. La meta de 20 commits es una constante configurable.
- **Revisiones:** porcentaje de pull requests con al menos `minReviewers` revisores. Sin PRs vale 0.
- **Consistencia:** de las últimas 4 semanas, el porcentaje que tuvo al menos un commit.

`minReviewers` sale de `scrapingConfig` del curso (por defecto 1).

## 2. Asociación criterio-métrica

Cada criterio de la rúbrica usa una métrica según su nombre (sin distinguir mayúsculas):

- Contiene `revis`: Revisiones.
- Contiene `consist` o `constan`: Consistencia.
- Cualquier otro nombre: Código.

## 3. Puntaje y progreso

- Puntaje del criterio: `round(peso × porcentaje / 100)`, con máximo igual al peso.
- Nota total (`score`): suma de los puntajes de los criterios. Los pesos de la rúbrica deben sumar 100 (se valida al guardar).
- Progreso (`progress`): promedio de las tres métricas, redondeado.

## 4. Niveles

- 80 o más: **Bueno**, tipo `success`.
- 60 a 79: **En progreso**, tipo `warning`.
- Menos de 60: **Bajo**, tipo `alert`.

## 5. Evidencia

Los 10 eventos más recientes del grupo: `id`, `type`, `text` (mensaje), `author`, `reviewer` (primer revisor o nulo) y `when` (Epoch en ms).

## 6. Inconvenientes

- **Commit de prueba:** un commit cuyo mensaje contiene como palabra suelta `test`, `prueba`, `wip`, `asdf` o `tmp`. Estado inicial `Sin resolver`.
- La detección es idempotente por `sourceEventId`: un commit genera un solo inconveniente.
- Cada inconveniente nuevo emite un evento `ISSUE_DETECTED` a la cola (si la cola falla, se registra el error y el inconveniente se conserva).
- Mejora opcional: **Error de entrega** (entrega fuera de plazo).

## 7. Retroalimentación

- Si el grupo no tiene retroalimentación, `GET` crea un borrador con el texto de IA: "El grupo obtiene X/100. Fortaleza: A (p%). A mejorar: B (q%)." (criterio con mayor y menor porcentaje).
- Publicar exige texto del profesor; si falta responde 400.
- Al publicar se guarda `status = published` y se emite `FEEDBACK_PUBLISHED`. Si la cola falla, la publicación se conserva y la respuesta indica `notified: false`.

## 8. Casos límite

- Curso sin rúbrica configurada: 404 `{"error": "..."}`.
- Grupo sin eventos: métricas en 0 y evidencia vacía.
- Parámetros de paginación fuera de rango: 400.

## 9. Limitaciones conocidas

- **Progreso vs. puntaje:** `progress` es un promedio simple de las 3 métricas, mientras que `score` utiliza la suma ponderada según los pesos de la rúbrica.
- **Deducción de métricas por nombre:** la métrica asignada a cada criterio de la rúbrica se deduce a partir de su nombre (palabras clave `revis`, `consist`/`constan`, y código por defecto).
- **Consistencia temporal:** el cálculo de la consistencia depende de la fecha y hora en que se realiza la consulta (evalúa las últimas 4 semanas respecto al instante actual).
- **Resolución de inconvenientes:** los inconvenientes detectados no se pueden marcar como resueltos (no existe endpoint ni flujo para cambiar el estado a `Resuelto`).
