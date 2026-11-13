"""Seed de datos de prueba de la Fase II para MS2 (cursos 1, 4, 5 y 6; grupos de MS1).

Uso (desde la raiz del repo, con COSMOS_CONNECTION_STRING en la sesion):
    $env:APIM_KEY = "<clave>"
    python -m scripts.seed_demo            # dry-run: no escribe nada
    python -m scripts.seed_demo --apply    # escribe en Cosmos

Idempotente: upsert por id / groupId / courseId. No toca el seed original (seed.py).
Las fechas del reporte salen de los eventos de MS1 (APIM, solo lectura).
"""
import argparse
import os
import random
import sys
import time

import httpx

from app.db.cosmos import (
    get_database,
    init_indexes,
    FEEDBACK_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
    REPORT_CHECKLIST_COLLECTION,
)
from app.models.course_settings import Rubric, Instructions, ScrapingConfig
from app.services import course_settings as cs
from app.services.analysis import get_group_analysis

APIM_BASE = os.environ.get(
    "APIM_BASE", "https://apimanagementcristopherarayavega.azure-api.net/revisatec"
)
DAY_MS = 86_400_000

COURSES = {
    1: {
        "criteria": [("Calidad del modelo y consultas SQL", 40), ("Revisiones entre pares", 35), ("Consistencia del avance", 25)],
        "instructions": "Priorizar el diseno del modelo relacional y la normalizacion. Senalar consultas sin indices y exigir revision cruzada de los scripts SQL antes de fusionar.",
        "frequency": "daily", "minReviewers": 1,
    },
    4: {
        "criteria": [("Calidad del codigo", 45), ("Revisiones entre pares", 30), ("Consistencia del avance", 25)],
        "instructions": "Evaluar la correccion del analizador y la cobertura de casos de prueba. Valorar commits pequenos y descriptivos.",
        "frequency": "weekly", "minReviewers": 1,
    },
    5: {
        "criteria": [("Calidad de codigo y patrones de diseno", 40), ("Revisiones entre pares", 40), ("Consistencia del avance", 20)],
        "instructions": "Verificar el uso justificado de patrones de diseno y la separacion de capas. Cada pull request requiere dos revisores.",
        "frequency": "daily", "minReviewers": 2,
    },
    6: {
        "criteria": [("Calidad de los entregables", 40), ("Revision de pares", 30), ("Constancia del equipo", 30)],
        "instructions": "Revisar que los entregables del plan esten actualizados y que los riesgos tengan responsable y fecha. Valorar la constancia semanal.",
        "frequency": "weekly", "minReviewers": 1,
    },
}

# commits/prs: cantidades; weeks: semanas (0 = la mas reciente) con actividad; reviewed: PRs con revisores suficientes
GROUPS = {
    1: dict(name="Grupo 1 - Sistema de Inventario", course=1, commits=18, weeks=[0, 1, 2, 3], prs=4, reviewed=4, wip=1,
            topics=["tabla de productos", "consulta de existencias", "procedimiento de reabastecimiento", "indice por codigo de barras", "vista de movimientos", "disparador de auditoria"]),
    5: dict(name="Grupo 2 - Gestion de Citas", course=1, commits=12, weeks=[0, 1, 3], prs=3, reviewed=2, wip=0,
            topics=["modelo de pacientes", "consulta de agenda", "restriccion de horarios", "vista de citas pendientes", "script de datos iniciales"]),
    4: dict(name="Grupo 1 - Analizador de Gramaticas", course=4, commits=15, weeks=[0, 1, 2, 3], prs=3, reviewed=3, wip=1,
            topics=["tokenizador", "calculo de conjuntos primero", "tabla LL(1)", "manejo de errores sintacticos", "generador de arbol de derivacion"]),
    6: dict(name="Grupo 2 - Interprete Funcional", course=4, commits=8, weeks=[0, 2], prs=2, reviewed=1, wip=2,
            topics=["evaluador de expresiones", "cierres lexicos", "funciones de orden superior", "entorno de variables"]),
    7: dict(name="Grupo 1 - Plataforma de Reservas", course=5, commits=20, weeks=[0, 1, 2, 3], prs=5, reviewed=5, wip=0,
            topics=["patron repositorio", "servicio de reservas", "controlador REST", "patron fabrica de notificaciones", "validacion de disponibilidad", "capa de persistencia"]),
    8: dict(name="Grupo 2 - App de Notificaciones", course=5, commits=14, weeks=[0, 1, 2], prs=4, reviewed=3, wip=1,
            topics=["patron observador", "canal de correo", "plantillas de mensaje", "cola de envio", "preferencias de usuario"]),
    9: dict(name="Grupo 1 - Plan de Proyecto ERP", course=6, commits=10, weeks=[0, 1, 3], prs=2, reviewed=2, wip=0,
            topics=["cronograma del proyecto", "matriz de interesados", "estimacion de costos", "plan de comunicaciones"]),
    10: dict(name="Grupo 2 - Gestion de Riesgos", course=6, commits=6, weeks=[1, 3], prs=2, reviewed=0, wip=1,
            topics=["registro de riesgos", "matriz de probabilidad e impacto", "plan de mitigacion", "seguimiento de riesgos"]),
}


def fetch_ms1_events(course_id, key):
    r = httpx.get(f"{APIM_BASE}/calendar/events", params={"courseId": course_id, "pageSize": 100},
                  headers={"Ocp-Apim-Subscription-Key": key}, timeout=120)
    r.raise_for_status()
    return r.json().get("items", [])


def fetch_ms1_members(group_id, key):
    """Obtiene los integrantes del grupo desde MS1 y devuelve la lista de githubUser sin vacíos."""
    r = httpx.get(
        f"{APIM_BASE}/groups/{group_id}/members",
        headers={"Ocp-Apim-Subscription-Key": key},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        raw_members = data.get("members") or data.get("items") or []
    elif isinstance(data, list):
        raw_members = data
    else:
        raw_members = []

    users = []
    for m in raw_members:
        if isinstance(m, dict):
            u = m.get("githubUser")
            if u and isinstance(u, str) and u.strip():
                users.append(u.strip())
        elif isinstance(m, str) and m.strip():
            users.append(m.strip())
    return list(dict.fromkeys(users))


def build_events(gid, g, min_reviewers, now_ms, apply=False):
    if len(g["authors"]) <= min_reviewers:
        warning_msg = (
            f"Advertencia: grupo {gid} ({g['name']}, curso {g.get('course')}) "
            f"tiene {len(g['authors'])} integrante(s) y minReviewers={min_reviewers} "
            f"(el autor del PR no puede revisarse a sí mismo)."
        )
        if not apply:
            print(warning_msg)
        elif g.get("reviewed", 0) > 0:
            sys.exit(warning_msg)

    rng = random.Random(gid)
    prefixes = ["feat", "fix", "docs", "refactor", "chore"]
    events = []
    for i in range(g["commits"]):
        week = g["weeks"][i % len(g["weeks"])]
        days = week * 7 + rng.randint(1, 6)
        topic = g["topics"][i % len(g["topics"])]
        if i < g["wip"]:
            msg = f"{'wip' if i % 2 == 0 else 'prueba'}: {topic}"
        else:
            msg = f"{prefixes[i % len(prefixes)]}: {topic}"
        events.append({"id": f"g{gid}_c{i + 1:02d}", "groupId": gid, "type": "commit",
                       "author": g["authors"][i % len(g["authors"])], "reviewers": [], "message": msg,
                       "createdAt": now_ms - days * DAY_MS - rng.randint(0, 40_000_000)})
    for j in range(g["prs"]):
        week = g["weeks"][j % len(g["weeks"])]
        days = week * 7 + rng.randint(1, 6)
        author = g["authors"][j % len(g["authors"])]
        others = [a for a in g["authors"] if a != author]
        reviewers = others[:max(min_reviewers, 1)] if j < g["reviewed"] else []
        events.append({"id": f"g{gid}_pr{j + 1:02d}", "groupId": gid, "type": "pr", "author": author,
                       "reviewers": reviewers, "message": f"PR #{j + 1}: {g['topics'][j % len(g['topics'])]}",
                       "createdAt": now_ms - days * DAY_MS - rng.randint(0, 40_000_000)})
    return events


def run(apply, ms1_events=None, ms1_members=None):
    key = os.environ.get("APIM_KEY", "")
    now_ms = int(time.time() * 1000)
    if (ms1_events is None or ms1_members is None) and not key:
        sys.exit("Falta $env:APIM_KEY (se usa solo para LEER los eventos e integrantes de MS1).")

    if ms1_events is None:
        ms1_events = {c: fetch_ms1_events(c, key) for c in COURSES}
    for c, evs in ms1_events.items():
        if not evs:
            sys.exit(f"MS1 no devolvio eventos para el curso {c}; no hay fechas para el reporte.")

    if ms1_members is None:
        ms1_members = {gid: fetch_ms1_members(gid, key) for gid in GROUPS}

    for gid in GROUPS:
        authors = ms1_members.get(gid) or []
        if not authors:
            sys.exit(f"MS1 no devolvió integrantes con githubUser para el grupo {gid}.")
        GROUPS[gid]["authors"] = authors

    print(f"Modo: {'APLICAR' if apply else 'DRY-RUN (no escribe)'}")
    for cid, c in COURSES.items():
        print(f"curso {cid}: rubrica {len(c['criteria'])} criterios (suman {sum(w for _, w in c['criteria'])}), "
              f"scraping {c['frequency']}/min {c['minReviewers']}, reporte {len(ms1_events[cid])} hitos de MS1")
    plan = {}
    for gid, g in GROUPS.items():
        evs = build_events(gid, g, COURSES[g["course"]]["minReviewers"], now_ms, apply=apply)
        plan[gid] = evs
        n_issue = sum(1 for e in evs if e["type"] == "commit" and e["message"].split(":")[0] in ("wip", "prueba"))
        authors_str = ", ".join(g["authors"])
        print(f"grupo {gid} ({g['name']}, curso {g['course']}): autores=[{authors_str}], {len(evs)} eventos, {n_issue} inconvenientes esperados")
    if not apply:
        return plan

    db = get_database()
    init_indexes(db)
    for cid, c in COURSES.items():
        cs.update_rubric(cid, Rubric(criteria=[{"name": n, "weight": float(w)} for n, w in c["criteria"]]))
        cs.update_instructions(cid, Instructions(text=c["instructions"]))
        cs.update_scraping_config(cid, ScrapingConfig(frequency=c["frequency"], minReviewers=c["minReviewers"]))

    for gid, g in GROUPS.items():
        cid = g["course"]
        evs = sorted(ms1_events[cid], key=lambda e: e["date"])
        # 1) feedback base (fija courseId, que usa get_course_id_for_group)
        pending = [e for e in evs if e["date"] >= now_ms]
        delivery = (pending[0] if pending else evs[-1])["title"]
        db[FEEDBACK_COLLECTION].update_one(
            {"groupId": gid},
            {"$set": {"courseId": cid, "groupName": g["name"], "deliveryTitle": delivery, "updatedAt": now_ms},
             "$setOnInsert": {"professor": "", "status": "draft", "publishedAt": None, "ai": None, "score": None}},
            upsert=True)
        # 2) eventos y checklist
        for ev in plan[gid]:
            db[GITHUB_EVENTS_COLLECTION].update_one({"id": ev["id"]}, {"$set": ev}, upsert=True)
        for e in evs:
            item = {"groupId": gid, "name": e["title"], "date": int(e["date"]),
                    "status": "completado" if e["date"] < now_ms else "pendiente"}
            db[REPORT_CHECKLIST_COLLECTION].update_one({"groupId": gid, "name": item["name"]}, {"$set": item}, upsert=True)
        # 3) texto IA y nota con las reglas de docs/reglas-rubrica.md (solo si sigue en borrador)
        doc = db[FEEDBACK_COLLECTION].find_one({"groupId": gid})
        if doc.get("status") != "published":
            a = get_group_analysis(gid)
            if a.criteria:
                best = max(a.criteria, key=lambda c: c.percent)
                worst = min(a.criteria, key=lambda c: c.percent)
                if len(a.criteria) == 1 or best.percent == worst.percent:
                    ai = (f"El grupo obtiene {int(round(a.score))}/100. "
                          f"Rendimiento parejo en todos los criterios ({best.percent}%).")
                else:
                    ai = (f"El grupo obtiene {int(round(a.score))}/100. Fortaleza: {best.name} ({best.percent}%). "
                          f"A mejorar: {worst.name} ({worst.percent}%).")
            else:
                ai = f"El grupo obtiene {int(round(a.score))}/100."
            db[FEEDBACK_COLLECTION].update_one({"groupId": gid}, {"$set": {"ai": ai, "score": float(a.score)}})
        print(f"grupo {gid}: OK")
    print("Listo. Verifica con GET por APIM (analysis, criteria, report, feedback). NO llames /issues aun: emite eventos a la cola.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="escribe en Cosmos (sin esto es dry-run)")
    run(p.parse_args().apply)
