"""Fase 1 del reto · El orquestador de la fábrica como grafo de LangGraph.

Cada nodo ejecuta un skill con `claude -p`, valida su artefacto con el código (validadores/ y verificacion/)
y actualiza el estado. Un nodo nunca se da por bueno porque `is_error` sea False: se juzga por su artefacto
(existe, cambió su mtime y valida). Las pausas con persona usan `interrupt` y `Command(resume=...)`.

Uso:
    python -m flujos.fabrica historias/HU-01-registrar-empleado.md [--aprobar]
    python -m flujos.fabrica historias/HU-01-registrar-empleado.md --ensayo [--escenario e2e_pruebas]
    python -m flujos.fabrica --reanudar HU-01-20261115-101500
    python -m flujos.fabrica --diagrama                      (solo exporta docs/grafo.mmd)

Orden: filtro → criterios → preguntas → casos → plan → aprobación → código → despliegue ∥ pruebas
→ e2e → (triage → corrección → e2e)* → revisión → reporte.
"""
import argparse
import json
import operator
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, RetryPolicy, interrupt

import verificacion
from flujos import claude
from flujos.claude import ErrorInfraestructura
from flujos.documentador import DocumentadorReal, ResultadoDocumentacion
from flujos.revisor import ResultadoRevision, RevisorReal, formatear_observaciones
from validadores.contratos import Diagnostico, Observacion, preguntas_abiertas
from validadores.validar import problemas_de
from verificacion import sandbox

RAIZ = Path(__file__).resolve().parent.parent

# --- Topes: todo bucle tiene un límite -----------------------------------------------------------
MAX_RECHAZOS = 2             # el plan se puede rechazar 2 veces; el 3.º rechazo escala a una persona
MAX_INTENTOS_CONSTRUIR = 2   # la construcción y un reintento con el log
MAX_CICLOS = 2               # ciclos triage → corrección → e2e
MAX_CICLOS_REVISION = 1      # fase 2: si el revisor rechaza, un solo ciclo de corrección

def calcular_recursion_limit(margen: int = 10) -> int:
    """Pasos (supersteps) del peor camino del grafo, derivados de los topes, más un margen.

    Cada nodo terminado es un paso; el límite de LangGraph cuenta pasos, no nodos distintos:
      6                       filtrar, analizar, preguntas, disenar, planificar, aprobar_plan
      2 · MAX_RECHAZOS        cada rechazo del plan repite planificar y aprobar_plan
      MAX_INTENTOS_CONSTRUIR  construir (la construcción y su reintento)
      3                       desplegar ∥ automatizar (un paso), listo y el primer e2e
      3 · MAX_CICLOS          cada ciclo de corrección: triage, corregir_*, e2e
      1 + 3 · MAX_CICLOS_REVISION   revisar, y por cada rechazo: corregir_codigo, e2e, revisar
      2                       documentar y reporte
    Con los topes actuales son 27 pasos y con el margen de 10, 37. El margen cubre que el subgrafo de corrección y
    los reintentos por infraestructura no suman pasos al principal, pero no deben dejar sin holgura a un camino legítimo.
    """
    pasos = (6 + 2 * MAX_RECHAZOS + MAX_INTENTOS_CONSTRUIR + 3 + 3 * MAX_CICLOS
             + 1 + 3 * MAX_CICLOS_REVISION + 2)
    return pasos + margen


RECURSION_LIMIT = calcular_recursion_limit()
ESPERA_REINTENTO = 30.0      # s antes del segundo intento tras un fallo de infraestructura (backoff por defecto de LangGraph)
MOTIVO_INFRAESTRUCTURA = "`claude -p` no respondió (sin JSON o tiempo agotado) tras 2 intentos"      # fijo: nunca texto crudo


def config_de(thread_id: str) -> dict:
    """El config de una corrida: su thread (para reanudar) y el límite de pasos calculado desde los topes."""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


# Estados finales posibles (los mismos cuatro que el reporte de /fabrica)
LISTA = "LISTA"
BLOQUEADA = "BLOQUEADA POR SEGURIDAD"
DETENIDA = "DETENIDA POR LA PERSONA"
ESCALAR = "ESCALAR A UNA PERSONA"

# Cada llamada fija su modelo: nada se hereda de la sesión
MODELOS = {
    "filtrar": "haiku", "criterios": "sonnet", "casos": "sonnet", "plan": "sonnet",
    "construir": "sonnet", "desplegar": "sonnet", "automatizar": "sonnet", "triage": "sonnet",
    "revisar": "sonnet", "documentar": "haiku",
}


class Estado(TypedDict, total=False):
    """Estado del grafo. Los campos con reducer se acumulan; el resto se sobrescribe."""

    historia: str                    # ruta de la historia; el orquestador NUNCA lee su contenido
    hu: str                          # HU-xx, sale del nombre del archivo
    base: str                        # commit al arrancar la corrida: la base de lo que revisa el revisor
    sospechosa: bool                 # único dato del veredicto que usa el flujo
    preguntas: list[str]
    rechazos: int
    comentarios: str                 # comentarios de la persona sobre el plan
    plan_aprobado: bool
    intentos: int                    # construcciones hechas
    log_app: str
    app_ok: bool
    despliegue_ok: bool
    pruebas_ok: bool
    e2e_ok: bool
    log_e2e: str
    log_correccion: str              # log de una corrección de código que no verificó o no se redesplegó
    ciclos: int                      # ciclos de corrección por e2e
    responsable: str
    instruccion: str                 # qué debe corregir el responsable (diagnóstico del triage u observaciones)
    revisiones: int                  # ciclos de corrección por rechazo del revisor
    revision_ok: bool
    documentacion_ok: bool           # documentacion.md escrito en esta corrida
    estado_final: str
    costo_usd: Annotated[float, operator.add]
    bitacora: Annotated[list[str], operator.add]
    eventos_seguridad: Annotated[list[dict], operator.add]


# --- Servicios: lo que el grafo necesita del mundo (se sustituye en el ensayo) -----------------------
@dataclass
class Servicios:
    """Dependencias externas del grafo: llamar al modelo, verificar y dónde se escribe `salida/`."""

    ejecutar: Callable[..., dict]                               # (prompt, *, modelo) -> dict de claude.ejecutar
    verificar: Callable[[str, str | None], tuple[bool, str]]    # (nombre, hu) -> (ok, log), como verificacion
    salida: Path
    app: Path                                                   # carpeta app/ cuyos cambios vigila construir
    registros: Path                                             # detalle de seguridad: ningún rol de hooks/roles.py lo lee
    revisor: Callable[[str, str], ResultadoRevision]            # (hu, commit base) -> ResultadoRevision
    documentador: Callable[[str, str], ResultadoDocumentacion]  # (hu, commit base) -> ResultadoDocumentacion


def servicios_reales() -> Servicios:
    """Servicios de verdad: `claude -p`, las verificaciones de verificacion/, el revisor real y salida/ del proyecto."""
    return Servicios(ejecutar=claude.ejecutar_exigiendo, verificar=verificacion.verificar, salida=RAIZ / "salida",
                     app=RAIZ / "app", registros=RAIZ / "registros",
                     revisor=RevisorReal(ejecutar=claude.ejecutar_exigiendo, raiz=RAIZ, modelo=MODELOS["revisar"]),
                     documentador=DocumentadorReal(ejecutar=claude.ejecutar_exigiendo, raiz=RAIZ, modelo=MODELOS["documentar"]))


def _git_raiz(*args: str, raiz: Path = RAIZ) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def precondicion_app(raiz: Path = RAIZ) -> str | None:
    """Una corrida real exige app/ limpia en git: si no, el revisor no sabría qué cambió en la corrida.

    Devuelve el mensaje de error, o None si se puede arrancar.
    """
    r = _git_raiz("status", "--porcelain", "app/", raiz=raiz)
    if r.returncode != 0:
        return f"No se pudo consultar git: {r.stderr.strip()}"
    if r.stdout.strip():
        return ("app/ tiene cambios sin commitear; la fábrica no arranca así porque el revisor revisa lo que cambia "
                "en la corrida. Haz commit o descarta estos cambios:\n" + r.stdout.rstrip())
    return None


def precondicion_sandbox() -> str | None:
    """Una corrida real exige Docker y las dos imágenes del sandbox (fabrica-sandbox:1 y fabrica-sandbox-node:1).

    Devuelve el mensaje (con el comando para construirlas) o None. El código generado nunca corre en el anfitrión.
    """
    return sandbox.precondicion()


def commit_base(raiz: Path = RAIZ) -> str:
    """El commit actual: la base de lo que revisa el revisor."""
    r = _git_raiz("rev-parse", "HEAD", raiz=raiz)
    if r.returncode != 0:
        raise RuntimeError(f"No se pudo leer el commit base: {r.stderr.strip()}")
    return r.stdout.strip()


# --- Utilidades de nodos -----------------------------------------------------------------------------
def costo_de(respuesta: dict) -> float:
    """Costo en USD de una respuesta de `ejecutar` (0 si no vino)."""
    return float(respuesta.get("total_cost_usd") or 0.0)


def producir_artefacto(sv: Servicios, ruta: Path, prompt: str, clave_modelo: str) -> tuple[list[str], float]:
    """Ejecuta un skill y juzga su artefacto: debe existir, haber cambiado de mtime y validar.

    Devuelve (problemas, costo). Lista vacía = el artefacto es bueno, sin importar `is_error`.
    """
    antes = ruta.stat().st_mtime_ns if ruta.exists() else None
    respuesta = sv.ejecutar(prompt, modelo=MODELOS[clave_modelo])
    costo = costo_de(respuesta)
    if not ruta.exists():
        return [f"el agente no escribió {ruta.name}"], costo
    if antes is not None and ruta.stat().st_mtime_ns == antes:
        return [f"{ruta.name} no cambió después de ejecutar el skill"], costo
    problemas = problemas_de(ruta)
    if problemas is None:
        return [f"no hay validador para {ruta.name}"], costo
    return problemas, costo


def falla(paso: str, problemas: list[str], costo: float = 0.0) -> dict:
    """Actualización de estado cuando un paso no produjo un artefacto válido: escala a una persona."""
    return {"estado_final": ESCALAR, "costo_usd": costo,
            "bitacora": [f"{paso}: ESCALAR · " + "; ".join(problemas)]}


PRIVADOS = ("motivo", "problemas")      # texto que puede venir del modelo: solo vive en registros/
_LOCK_SEGURIDAD = threading.Lock()      # el lote (flujos/lote.py) llama a registrar_seguridad desde varios hilos a la vez


def registrar_seguridad(sv: Servicios, hu: str, eventos: list[dict]) -> list[dict]:
    """Agrega los eventos completos a registros/seguridad.jsonl SIEMPRE (también con DEFENSAS=0).

    Devuelve la versión PÚBLICA (sin motivo ni problemas) para el estado: así el motivo no llega al checkpoint
    ni al reporte, que viven en salida/ y sí pueden leer los agentes.
    """
    completos = [{"ts": round(time.time(), 1), "hu": hu, **e} for e in eventos]
    sv.registros.mkdir(parents=True, exist_ok=True)
    with _LOCK_SEGURIDAD, open(sv.registros / "seguridad.jsonl", "a", encoding="utf-8") as f:
        f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in completos)
    return [{k: v for k, v in e.items() if k not in PRIVADOS} for e in completos]


def huella_app(app: Path) -> dict[str, int]:
    """Huella de app/backend y app/frontend/src: ruta → mtime. Excluye node_modules, dist, datos y __pycache__."""
    excluidos = {"node_modules", "dist", "datos", "__pycache__"}
    huella = {}
    for base in (app / "backend", app / "frontend" / "src"):
        for ruta in base.rglob("*") if base.exists() else []:
            if ruta.is_file() and not excluidos & set(ruta.relative_to(app).parts):
                huella[ruta.relative_to(app).as_posix()] = ruta.stat().st_mtime_ns
    return huella


def ultimas_lineas(texto: str, n: int = 40) -> str:
    """Las últimas n líneas de un log, para pasarlas a un agente sin inundarlo."""
    return "\n".join(texto.splitlines()[-n:])


# --- Nodos -------------------------------------------------------------------------------------------
def nodo_filtrar(sv: Servicios, s: Estado) -> dict:
    """Filtro de seguridad: /filtrar → veredicto.json. Solo el booleano `sospechosa` entra al flujo.

    El motivo del veredicto va únicamente a registros/seguridad.jsonl: nunca a un prompt, ni al estado, ni a salida/.
    """
    hu = s["hu"]
    _, estado_defensas = sv.verificar("defensas", hu)
    activas = "DESACTIVADAS" not in estado_defensas
    eventos = [{"evento": "defensas", "activas": activas, "detalle": estado_defensas.strip()}]
    if not activas:
        eventos.append({"evento": "filtro_omitido"})
        return {"sospechosa": False, "eventos_seguridad": registrar_seguridad(sv, hu, eventos),
                "bitacora": ["Filtro de historia DESACTIVADO (DEFENSAS=0)"]}
    ruta = sv.salida / hu / "veredicto.json"
    problemas, costo = producir_artefacto(sv, ruta, f"/filtrar {s['historia']}", "filtrar")
    contenido = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    if ruta.exists():                               # el agente deja el motivo en salida/ (que otros agentes leen):
        destino = sv.registros / hu / "veredicto.json"     # el código lo mueve a registros/ apenas lo lee
        destino.parent.mkdir(parents=True, exist_ok=True)
        ruta.replace(destino)
    if problemas:                                   # sin veredicto válido no se avanza: falla cerrado
        eventos.append({"evento": "veredicto_invalido", "problemas": problemas})
        return {**falla("Filtro de seguridad", problemas, costo),
                "eventos_seguridad": registrar_seguridad(sv, hu, eventos)}
    veredicto = json.loads(contenido)
    sospechosa = bool(veredicto["sospechosa"])
    eventos.append({"evento": "veredicto", "sospechosa": sospechosa, "motivo": veredicto.get("motivo", "")})
    if sospechosa:
        eventos.append({"evento": "bloqueo", "razon": "historia sospechosa"})
    return {"sospechosa": sospechosa, "costo_usd": costo,
            "eventos_seguridad": registrar_seguridad(sv, hu, eventos),
            **({"estado_final": BLOQUEADA} if sospechosa else {}),
            "bitacora": [f"Filtro de seguridad: {'BLOQUEADA' if sospechosa else 'OK'}"]}


def nodo_analizar(sv: Servicios, s: Estado) -> dict:
    """Analista: /criterios → criterios.feature válido."""
    ruta = sv.salida / s["hu"] / "criterios.feature"
    problemas, costo = producir_artefacto(sv, ruta, f"/criterios {s['historia']}", "criterios")
    if problemas:
        return falla("Criterios", problemas, costo)
    return {"costo_usd": costo, "bitacora": ["Criterios escritos en criterios.feature"]}


def nodo_preguntas(sv: Servicios, s: Estado) -> dict:
    """Preguntas abiertas: las lee el código; si hay, una persona decide si se continúa (interrupt)."""
    texto = (sv.salida / s["hu"] / "criterios.feature").read_text(encoding="utf-8")
    lista = preguntas_abiertas(texto)
    if not lista:
        return {"preguntas": [], "bitacora": ["Sin preguntas abiertas"]}
    respuesta = interrupt({"preguntas": lista,
                           "pregunta": "Hay preguntas abiertas. ¿Continuar de todos modos? (si/no)"})
    if respuesta.strip().lower() == "si":
        return {"preguntas": lista, "bitacora": [f"{len(lista)} preguntas abiertas: la persona continúa"]}
    return {"preguntas": lista, "estado_final": DETENIDA,
            "bitacora": [f"{len(lista)} preguntas abiertas: la persona detiene el flujo"]}


def nodo_disenar(sv: Servicios, s: Estado) -> dict:
    """Diseñador de pruebas: /casos → casos_prueba.json válido y que cubre cada escenario."""
    hu = s["hu"]
    ruta = sv.salida / hu / "casos_prueba.json"
    problemas, costo = producir_artefacto(sv, ruta, f"/casos salida/{hu}/criterios.feature", "casos")
    if problemas:
        return falla("Casos de prueba", problemas, costo)
    return {"costo_usd": costo, "bitacora": ["Casos de prueba escritos en casos_prueba.json"]}


def nodo_planificar(sv: Servicios, s: Estado) -> dict:
    """Arquitecto: /plan (con los comentarios de la persona si el plan anterior se rechazó) → plan.md válido."""
    hu = s["hu"]
    comentarios = s.get("comentarios", "").strip()
    prompt = f"/plan {hu}" + (f" {comentarios}" if comentarios else "")
    problemas, costo = producir_artefacto(sv, sv.salida / hu / "plan.md", prompt, "plan")
    if problemas:
        return falla("Plan", problemas, costo)
    return {"costo_usd": costo, "bitacora": ["Plan escrito en plan.md" + (" (con comentarios)" if comentarios else "")]}


def nodo_aprobar_plan(sv: Servicios, s: Estado) -> dict:
    """Aprobación humana del plan (interrupt). Rechazos 1 y 2 replanifican; el 3.º escala."""
    plan = (sv.salida / s["hu"] / "plan.md").read_text(encoding="utf-8")
    decision = interrupt({"plan": plan, "pregunta": "¿Apruebas el plan? Escribe si o tus comentarios"})
    if decision.strip().lower() == "si":
        return {"plan_aprobado": True, "bitacora": ["Plan aprobado por una persona"]}
    rechazos = s.get("rechazos", 0) + 1
    actualiza = {"plan_aprobado": False, "comentarios": decision, "rechazos": rechazos,
                 "bitacora": [f"Plan rechazado ({rechazos}): {decision}"]}
    if rechazos > MAX_RECHAZOS:
        actualiza |= {"estado_final": ESCALAR}
        actualiza["bitacora"].append(f"Más de {MAX_RECHAZOS} rechazos: ESCALAR")
    return actualiza


def nodo_construir(sv: Servicios, s: Estado) -> dict:
    """Desarrollador: /construir; decide el código: app/ debe haber cambiado Y verificacion app debe pasar.

    Si falla (también si el agente no tocó app/), un reintento con el log.

    OJO, intencional: el subagente desarrollador ya tiene su propia compuerta (SubagentStop, máx 2), así que con
    el reintento del grafo son hasta 3 intentos de corregir antes de escalar.

    Reintento por infraestructura (RetryPolicy): si `claude -p` no responde, LangGraph repite el nodo ENTERO. La huella
    de app/ se mide DENTRO de cada intento, así que un intento cortado a medias pudo dejar cambios en app/ y el
    reintento parte de esa huella ya modificada: si el reintento no vuelve a tocar app/, cuenta como intento fallido
    aunque el código a medias fuera bueno. No se cambia la lógica: es preferible escalar a dar por bueno un cambio que
    nadie verificó.
    """
    hu = s["hu"]
    intentos = s.get("intentos", 0)
    correccion = ""
    if intentos > 0:
        correccion = f" La verificación falló; corrige esto:\n{ultimas_lineas(s.get('log_app', ''))}"
    antes = huella_app(sv.app)
    respuesta = sv.ejecutar(f"/construir {hu}{correccion}", modelo=MODELOS["construir"])
    if huella_app(sv.app) == antes:                 # sin cambios en app/ no hay nada que verificar: intento fallido
        ok, log = False, "el desarrollador no modificó app/"
    else:
        ok, log = sv.verificar("app", hu)           # el código decide, no el agente
    actualiza = {"intentos": intentos + 1, "app_ok": ok, "log_app": log, "costo_usd": costo_de(respuesta),
                 "bitacora": [f"Construcción {intentos + 1}: verificación {'OK' if ok else 'FALLA'}"]}
    if not ok and intentos + 1 >= MAX_INTENTOS_CONSTRUIR:
        actualiza |= {"estado_final": ESCALAR}
        actualiza["bitacora"].append("La app no pasa la verificación tras el reintento: ESCALAR")
    return actualiza


def _con_reintento(sv: Servicios, hu: str, skill: str, clave: str, verificacion_: str, texto_error: str) -> tuple[bool, str, float]:
    """Corre un skill y su verificación; si falla, lo repite UNA vez pasándole el log. Devuelve (ok, log, costo)."""
    costo, errores, ok, log = 0.0, "", False, ""
    for _ in range(2):
        prompt = f"/{skill} {hu}" + (f" {texto_error}\n{ultimas_lineas(errores)}" if errores else "")
        costo += costo_de(sv.ejecutar(prompt, modelo=MODELOS[clave]))
        ok, log = sv.verificar(verificacion_, hu)
        if ok:
            break
        errores = log
    return ok, log, costo


def nodo_desplegar(sv: Servicios, s: Estado) -> dict:
    """Despliegue (rama paralela): /desplegar y verificación `despliegue`, con un reintento."""
    ok, _, costo = _con_reintento(sv, s["hu"], "desplegar", "desplegar", "despliegue", "El despliegue anterior falló:")
    return {"despliegue_ok": ok, "costo_usd": costo, "bitacora": [f"Despliegue: {'OK' if ok else 'FALLA'}"]}


def nodo_automatizar(sv: Servicios, s: Estado) -> dict:
    """Automatizador (rama paralela): /automatizar y verificación `pruebas`, con un reintento."""
    ok, _, costo = _con_reintento(sv, s["hu"], "automatizar", "automatizar", "pruebas", "Las pruebas anteriores fallaron:")
    return {"pruebas_ok": ok, "costo_usd": costo, "bitacora": [f"Pruebas automatizadas: {'OK' if ok else 'FALLA'}"]}


def nodo_listo(sv: Servicios, s: Estado) -> dict:
    """Unión de las ramas paralelas: sigue a e2e solo si ambas terminaron bien."""
    if s.get("despliegue_ok") and s.get("pruebas_ok"):
        return {"bitacora": ["Despliegue y pruebas listos"]}
    return {"estado_final": ESCALAR, "bitacora": ["Despliegue o pruebas con FALLA: ESCALAR"]}


def nodo_e2e(sv: Servicios, s: Estado) -> dict:
    """Pruebas de punta a punta: `verificacion e2e` deja resultados.xml y fallos.md para el triage."""
    ok, log = sv.verificar("e2e", s["hu"])
    resumen = log.strip().splitlines()[0] if log.strip() else "sin salida"
    actualiza = {"e2e_ok": ok, "log_e2e": log, "bitacora": [f"Pruebas E2E: {resumen}"]}
    if not ok and s.get("ciclos", 0) >= MAX_CICLOS:
        actualiza |= {"estado_final": ESCALAR}
        actualiza["bitacora"].append(f"E2E sigue fallando tras {MAX_CICLOS} ciclos de corrección: ESCALAR")
    return actualiza


def nodo_triage(sv: Servicios, s: Estado) -> Command:
    """Triage: /triage → diagnostico.json válido; enruta con Command(goto=...) al responsable (no corrige)."""
    hu = s["hu"]
    ruta = sv.salida / hu / "diagnostico.json"
    problemas, costo = producir_artefacto(sv, ruta, f"/triage {hu}", "triage")
    if problemas:
        return Command(update=falla("Triage", problemas, costo), goto=END)   # termina el subgrafo; el principal va a reporte
    d = Diagnostico.model_validate_json(ruta.read_text(encoding="utf-8"))
    destino = {"desarrollador": "corregir_codigo", "automatizador": "corregir_pruebas",
               "despliegue": "corregir_despliegue"}[d.responsable]
    return Command(update={"responsable": d.responsable, "instruccion": f"{d.causa}\n{d.instruccion}",
                           "ciclos": s.get("ciclos", 0) + 1, "costo_usd": costo,
                           "bitacora": [f"Triage → {d.responsable}: {d.causa}"]},
                   goto=destino)


def nodo_corregir_codigo(sv: Servicios, s: Estado) -> dict:
    """Corrige el código: /construir con la instrucción del diagnóstico; verifica la app y luego redespliega.

    Si la app no verifica o el redespliegue falla se escala con el log: no se sigue a e2e a ciegas.
    """
    hu = s["hu"]
    antes = huella_app(sv.app)
    costo = costo_de(sv.ejecutar(f"/construir {hu} Corrige: {s['instruccion']}", modelo=MODELOS["construir"]))
    if huella_app(sv.app) == antes:                 # igual que construir: sin cambios en app/ no hubo corrección
        return {"estado_final": ESCALAR, "log_correccion": "el desarrollador no modificó app/", "costo_usd": costo,
                "bitacora": ["Corrección de código sin cambios en app/: ESCALAR"]}
    for paso in ("app", "redespliegue"):            # primero la app; el código cambió y los contenedores tienen la vieja
        ok, log = sv.verificar(paso, hu)
        if not ok:
            return {"estado_final": ESCALAR, "log_correccion": log, "costo_usd": costo,
                    "bitacora": [f"Código corregido, pero «{paso}» FALLA: ESCALAR"]}
    return {"costo_usd": costo, "bitacora": ["Código corregido; app verificada y redespliegue OK"]}


def nodo_corregir_pruebas(sv: Servicios, s: Estado) -> dict:
    """Corrige las pruebas: /automatizar con la instrucción del diagnóstico."""
    respuesta = sv.ejecutar(f"/automatizar {s['hu']} Estas pruebas fallaron y el error está en la prueba: "
                            f"{s['instruccion']}", modelo=MODELOS["automatizar"])
    return {"costo_usd": costo_de(respuesta), "bitacora": ["Pruebas corregidas"]}


def nodo_corregir_despliegue(sv: Servicios, s: Estado) -> dict:
    """Corrige el despliegue: /desplegar con la instrucción del diagnóstico."""
    respuesta = sv.ejecutar(f"/desplegar {s['hu']} El despliegue falló: {s['instruccion']}",
                            modelo=MODELOS["desplegar"])
    return {"costo_usd": costo_de(respuesta), "bitacora": ["Despliegue corregido"]}


def nodo_revisar(sv: Servicios, s: Estado) -> dict:
    """Revisión de resultados, AL FINAL (después de e2e OK), con el revisor de flujos/revisor.py.

    La revisión completa va a registros/HU-xx/revision.json y un evento «revision» a registros/seguridad.jsonl
    (solo booleanos y conteos al estado). Si el revisor rechaza → corregir_codigo → e2e → revisar, con un máximo de
    MAX_CICLOS_REVISION ciclos; al agotarlo, o si el revisor escala, se escala. Las observaciones que llegan a
    corregir_codigo las formatea el código con los campos del esquema.
    """
    hu = s["hu"]
    r = sv.revisor(hu, s.get("base", ""))
    carpeta = sv.registros / hu
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "revision.json").write_text(json.dumps({
        "veredicto": r.veredicto, "motivo": r.motivo, "modelo_llamado": r.modelo_llamado, "base": s.get("base", ""),
        "observaciones": [o.model_dump() for o in r.observaciones],
        "informativas": [o.model_dump() for o in r.informativas]}, ensure_ascii=False, indent=2), encoding="utf-8")
    base = {"costo_usd": r.costo, "eventos_seguridad": registrar_seguridad(sv, hu, [{
        "evento": "revision", "veredicto": r.veredicto, "aprobada": r.veredicto == "aprobada",
        "modelo_llamado": r.modelo_llamado, "observaciones": len(r.observaciones)}])}
    if r.veredicto == "aprobada":
        return {**base, "revision_ok": True, "bitacora": ["Revisión: aprobada"]}
    if r.veredicto == "escalar":
        return {**base, "revision_ok": False, "estado_final": ESCALAR,
                "bitacora": [f"Revisión: ESCALAR · {r.motivo}"]}
    revisiones = s.get("revisiones", 0)
    if revisiones >= MAX_CICLOS_REVISION:
        return {**base, "revision_ok": False, "estado_final": ESCALAR,
                "bitacora": ["Revisión: el revisor sigue rechazando tras el ciclo de corrección: ESCALAR"]}
    return {**base, "revision_ok": False, "revisiones": revisiones + 1,
            "instruccion": formatear_observaciones(r.observaciones),
            "bitacora": [f"Revisión: rechazada ({len(r.observaciones)} observaciones)"]}


def nodo_documentar(sv: Servicios, s: Estado) -> dict:
    """Documentación de la historia, DESPUÉS de la revisión aprobada: el código arma salida/HU-xx/documentacion.md.

    El modelo solo aporta campos acotados (flujos/documentador.py); ausente o inválido → ESCALAR con un motivo fijo,
    sin reintentos. Al registro de seguridad va solo un evento con booleanos y un conteo.
    """
    hu = s["hu"]
    r = sv.documentador(hu, s.get("base", ""))
    eventos = registrar_seguridad(sv, hu, [{"evento": "documentacion", "generada": bool(r.markdown),
                                            "modelo_llamado": r.modelo_llamado, "no_verificados": r.no_verificados}])
    if not r.markdown:
        return {"estado_final": ESCALAR, "costo_usd": r.costo, "eventos_seguridad": eventos,
                "bitacora": [f"Documentación: ESCALAR · {r.motivo}"]}
    carpeta = sv.salida / hu
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "documentacion.md").write_text(r.markdown, encoding="utf-8")
    pendientes = f" ({r.no_verificados} sin verificar)" if r.no_verificados else ""
    return {"documentacion_ok": True, "costo_usd": r.costo, "eventos_seguridad": eventos,
            "bitacora": [f"Documentación escrita en documentacion.md{pendientes}"]}


def nodo_reporte(sv: Servicios, s: Estado) -> dict:
    """Escribe salida/HU-xx/reporte.md: estado, ciclos, costo, seguridad, bitácora y último log de e2e."""
    estado = s.get("estado_final") or (LISTA if s.get("e2e_ok") and s.get("revision_ok") else ESCALAR)
    carpeta = sv.salida / s["hu"]
    carpeta.mkdir(parents=True, exist_ok=True)
    lineas = [f"# Reporte · {s['hu']}", "", f"**Estado:** {estado}",
              f"**Ciclos de corrección:** {s.get('ciclos', 0)} (revisión: {s.get('revisiones', 0)})",
              f"**Costo de agentes:** {s.get('costo_usd', 0.0):.4f} USD", "", "## Seguridad"]
    eventos = s.get("eventos_seguridad", [])
    for e in eventos:                               # solo el evento y sus booleanos; el detalle queda fuera de salida/
        booleanos = ", ".join(f"{k}={v}" for k, v in e.items() if isinstance(v, bool))
        lineas.append(f"- {e['evento']}" + (f" ({booleanos})" if booleanos else ""))
    lineas += ["- (sin eventos)"] if not eventos else []
    lineas += ["", "Detalle en registros/seguridad.jsonl", "", "## Bitácora", *[f"- {b}" for b in s.get("bitacora", [])],
               "", "## Última ejecución de pruebas", "```", s.get("log_e2e", "(no se ejecutaron)"), "```", ""]
    if s.get("documentacion_ok"):                   # de ESTA corrida: un archivo viejo no cuenta
        lineas += ["## Documentación", "", "[documentacion.md](documentacion.md)", ""]
    if s.get("log_correccion"):
        lineas += ["## Corrección de código que no pasó", "```", ultimas_lineas(s["log_correccion"]), "```", ""]
    (carpeta / "reporte.md").write_text("\n".join(lineas), encoding="utf-8")
    return {"estado_final": estado}


# --- Aristas condicionales ---------------------------------------------------------------------------
def ruta_a(destino: str) -> Callable[[Estado], str]:
    """Arista condicional: sigue a `destino`, salvo que un nodo ya haya fijado el estado final (→ reporte)."""
    def decidir(s: Estado) -> str:
        """Decide entre el destino previsto y el reporte."""
        return "reporte" if s.get("estado_final") else destino
    return decidir


def tras_aprobar(s: Estado) -> str:
    """Plan aprobado → construir; rechazado → replanificar con los comentarios; estado final → reporte."""
    if s.get("estado_final"):
        return "reporte"
    return "construir" if s.get("plan_aprobado") else "planificar"


def tras_construir(s: Estado) -> list[str] | str:
    """App verificada → despliegue y automatización en paralelo; si no, reintento o reporte."""
    if s.get("estado_final"):
        return "reporte"
    return ["desplegar", "automatizar"] if s.get("app_ok") else "construir"


def tras_e2e(s: Estado) -> str:
    """e2e OK → revisar; falla → el subgrafo de corrección (que escala solo cuando se agotan los ciclos)."""
    if s.get("estado_final"):
        return "reporte"
    return "revisar" if s.get("e2e_ok") else "correccion"


def tras_revisar(s: Estado) -> str:
    """Estado final → reporte; revisión aprobada → documentar; rechazada → el subgrafo de corrección (entra por corregir_codigo)."""
    if s.get("estado_final"):
        return "reporte"
    return "documentar" if s.get("revision_ok") else "correccion"


# --- Grafo -------------------------------------------------------------------------------------------
LLAMAN_AL_MODELO = {"filtrar", "analizar", "disenar", "planificar", "construir", "desplegar", "automatizar",
                    "triage", "corregir_codigo", "corregir_pruebas", "corregir_despliegue", "revisar", "documentar"}


def politica_de_reintento(espera: float = ESPERA_REINTENTO) -> RetryPolicy:
    """Reintenta SOLO ErrorInfraestructura, una vez (2 intentos), esperando `espera` s con el backoff por defecto.

    Un fallo de infraestructura de `claude -p` rara vez se resuelve en el segundo siguiente, de ahí la espera de ~30 s.
    Un artefacto inválido no lanza esta excepción: no se reintenta y escala como siempre.
    """
    return RetryPolicy(max_attempts=2, initial_interval=espera, retry_on=ErrorInfraestructura)


def entrada_de_correccion(s: Estado) -> str:
    """Por dónde entra el subgrafo: con e2e fallando, por el triage; tras un rechazo del revisor (e2e ya pasó), por corregir_codigo."""
    return "corregir_codigo" if s.get("e2e_ok") else "triage"


def tras_corregir_codigo(s: Estado) -> str:
    """Dentro del subgrafo: si la corrección ya fijó el estado final (app rota, sin cambios…) sale; si no, vuelve a e2e."""
    return END if s.get("estado_final") else "e2e"


def tras_e2e_en_correccion(s: Estado) -> str:
    """Dentro del subgrafo: estado final o e2e OK → sale; si sigue fallando → otro triage (los topes los pone nodo_e2e)."""
    return END if s.get("estado_final") or s.get("e2e_ok") else "triage"


def construir_subgrafo_correccion(sv: Servicios, reintento: RetryPolicy) -> CompiledStateGraph:
    """El ciclo de corrección como subgrafo: triage → corregir_codigo / corregir_pruebas / corregir_despliegue → e2e.

    Mismo Estado y mismos topes que el grafo principal (MAX_CICLOS lo aplica nodo_e2e; el triage cuenta los ciclos).
    Sale por END: el principal decide después (reporte si hay estado final, revisar si no). Se compila SIN checkpointer:
    hereda el del principal.
    """
    g = StateGraph(Estado)
    g.add_node("triage", lambda s: nodo_triage(sv, s), retry_policy=reintento,
               destinations=("corregir_codigo", "corregir_pruebas", "corregir_despliegue", END))
    g.add_node("corregir_codigo", lambda s: nodo_corregir_codigo(sv, s), retry_policy=reintento)
    g.add_node("corregir_pruebas", lambda s: nodo_corregir_pruebas(sv, s), retry_policy=reintento)
    g.add_node("corregir_despliegue", lambda s: nodo_corregir_despliegue(sv, s), retry_policy=reintento)
    g.add_node("e2e", lambda s: nodo_e2e(sv, s))
    g.add_conditional_edges(START, entrada_de_correccion, ["triage", "corregir_codigo"])
    g.add_conditional_edges("corregir_codigo", tras_corregir_codigo, ["e2e", END])   # no sigue a ciegas si falló
    for correccion in ("corregir_pruebas", "corregir_despliegue"):
        g.add_edge(correccion, "e2e")                                   # el ciclo: corregir y volver a probar
    g.add_conditional_edges("e2e", tras_e2e_en_correccion, ["triage", END])
    return g.compile()


ACUMULADOS = {"costo_usd": 0.0, "bitacora": [], "eventos_seguridad": []}      # los campos con reducer de Estado


def nodo_correccion(subgrafo: CompiledStateGraph, s: Estado, config: RunnableConfig) -> dict:
    """Envoltorio del subgrafo de corrección: lo corre y devuelve SOLO lo que cambió.

    Un subgrafo compilado con el mismo Estado, agregado como nodo, devuelve su estado final completo y el principal
    lo fusiona con los reducers: el costo, la bitácora y los eventos de seguridad se contaban dos veces (comprobado en
    el ensayo e2e_codigo: 0.18 USD en lugar de 0.10). Por eso el subgrafo arranca con esos campos en blanco, así su
    salida son exactamente los deltas, y del resto se devuelven solo los campos que cambiaron.
    """
    salida = subgrafo.invoke({**s, **{k: type(v)() for k, v in ACUMULADOS.items()}}, config)
    return {k: v for k, v in salida.items() if k in ACUMULADOS or s.get(k) != v}


def construir_grafo(sv: Servicios, checkpointer, espera_reintento: float = ESPERA_REINTENTO) -> CompiledStateGraph:
    """Arma y compila el grafo de la fábrica con los servicios dados y un checkpointer (SqliteSaver)."""
    reintento = politica_de_reintento(espera_reintento)
    g = StateGraph(Estado)
    nodos = {"filtrar": nodo_filtrar, "analizar": nodo_analizar, "preguntas": nodo_preguntas,
             "disenar": nodo_disenar, "planificar": nodo_planificar, "aprobar_plan": nodo_aprobar_plan,
             "construir": nodo_construir, "desplegar": nodo_desplegar, "automatizar": nodo_automatizar,
             "listo": nodo_listo, "e2e": nodo_e2e,
             "revisar": nodo_revisar, "documentar": nodo_documentar, "reporte": nodo_reporte}
    for nombre, fn in nodos.items():
        g.add_node(nombre, lambda s, fn=fn: fn(sv, s), retry_policy=reintento if nombre in LLAMAN_AL_MODELO else None)
    subgrafo = construir_subgrafo_correccion(sv, reintento)
    g.add_node("correccion", lambda s, config: nodo_correccion(subgrafo, s, config))

    g.add_edge(START, "filtrar")
    g.add_conditional_edges("filtrar", ruta_a("analizar"), ["analizar", "reporte"])
    g.add_conditional_edges("analizar", ruta_a("preguntas"), ["preguntas", "reporte"])
    g.add_conditional_edges("preguntas", ruta_a("disenar"), ["disenar", "reporte"])
    g.add_conditional_edges("disenar", ruta_a("planificar"), ["planificar", "reporte"])
    g.add_conditional_edges("planificar", ruta_a("aprobar_plan"), ["aprobar_plan", "reporte"])
    g.add_conditional_edges("aprobar_plan", tras_aprobar, ["construir", "planificar", "reporte"])
    g.add_conditional_edges("construir", tras_construir, ["desplegar", "automatizar", "construir", "reporte"])
    g.add_edge(["desplegar", "automatizar"], "listo")                   # espera a que terminen ambas ramas
    g.add_conditional_edges("listo", ruta_a("e2e"), ["e2e", "reporte"])
    g.add_conditional_edges("e2e", tras_e2e, ["revisar", "correccion", "reporte"])
    g.add_conditional_edges("correccion", ruta_a("revisar"), ["revisar", "reporte"])   # mismas salidas que antes
    g.add_conditional_edges("revisar", tras_revisar, ["correccion", "documentar", "reporte"])
    g.add_edge("documentar", "reporte")
    g.add_edge("reporte", END)
    return g.compile(checkpointer=checkpointer)


def exportar_diagrama(app, ruta: Path = RAIZ / "docs" / "grafo.mmd") -> Path:
    """Guarda el grafo como Mermaid (get_graph(xray=True).draw_mermaid()) en docs/grafo.mmd.

    El nodo «correccion» es un envoltorio (una función que invoca al subgrafo), así que xray no muestra su interior:
    por eso el subgrafo se exporta aparte con exportar_diagrama_correccion.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(app.get_graph(xray=True).draw_mermaid(), encoding="utf-8")
    return ruta


def exportar_diagrama_correccion(sv: Servicios, ruta: Path = RAIZ / "docs" / "grafo-correccion.mmd") -> Path:
    """Guarda el subgrafo del ciclo de corrección como Mermaid en docs/grafo-correccion.mmd (evidencia de la entrega)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(construir_subgrafo_correccion(sv, politica_de_reintento()).get_graph().draw_mermaid(),
                    encoding="utf-8")
    return ruta


# --- Ejecución con pausas humanas --------------------------------------------------------------------
def estado_inicial(historia: str, base: str = "") -> Estado:
    """Estado de partida: la ruta y el HU-xx salen del NOMBRE del archivo (nunca se lee su contenido).

    `base` es el commit al arrancar (git rev-parse HEAD): lo que cambie después es lo que revisa el revisor.
    """
    hu = re.search(r"HU-\d+", Path(historia).name)
    if not hu:
        raise ValueError(f"El nombre de la historia debe contener HU-xx: {historia}")
    return {"historia": historia, "hu": hu.group(), "base": base, "rechazos": 0, "intentos": 0, "ciclos": 0, "revisiones": 0,
            "costo_usd": 0.0, "bitacora": [], "eventos_seguridad": []}


def nuevo_thread(hu: str) -> str:
    """thread_id único por corrida (HU-xx-AAAAMMDD-HHMMSS): evita arrastrar contadores de una corrida anterior."""
    return f"{hu}-{datetime.now():%Y%m%d-%H%M%S}"


SUBGRAFOS = {"correccion"}      # nodos del principal que envuelven un subgrafo (sus nodos internos salen con prefijo)


def linea_de_avance(ns: tuple, nodo: str, actualizacion, costo: float) -> str:
    """Una línea por nodo terminado: hora, nodo (con prefijo si es de un subgrafo), su línea de bitácora y el costo."""
    prefijo = "".join(f"{parte.split(':')[0]}/" for parte in ns)
    bitacora = actualizacion.get("bitacora") if isinstance(actualizacion, dict) else None
    return f"{datetime.now():%H:%M:%S}  {prefijo}{nodo}  ·  {bitacora[-1] if bitacora else '-'}  ·  {costo:.4f} USD"


def avanzar(app, cfg: dict, entrada, emitir: Callable[[str], None]) -> dict | None:
    """Corre el grafo con stream_mode="updates" hasta terminar o hasta una pausa humana (devuelve su valor).

    Imprime una línea por cada nodo terminado. El costo acumulado parte del estado guardado (también al reanudar)
    y suma el costo de cada actualización.
    """
    costo = app.get_state(cfg).values.get("costo_usd", 0.0)
    pausa = None
    for ns, trozo in app.stream(entrada, cfg, stream_mode="updates", subgraphs=True):
        if "__interrupt__" in trozo:                    # el interrupt llega como un trozo más del stream
            pausa = trozo["__interrupt__"][0].value
            continue
        for nodo, actualizacion in trozo.items():
            if isinstance(actualizacion, dict) and not (not ns and nodo in SUBGRAFOS):
                costo += actualizacion.get("costo_usd", 0.0)     # el nodo-envoltorio ya sumó los de sus nodos internos
            emitir(linea_de_avance(ns, nodo, actualizacion, costo))
    return pausa


def correr(app, cfg: dict, responder: Callable[[dict], str], entrada=None,
           emitir: Callable[[str], None] = print) -> dict:
    """Avanza el grafo (con streaming) y atiende cada pausa humana con `responder(pausa) -> texto` y Command(resume=...)."""
    try:
        pausa = avanzar(app, cfg, entrada, emitir)
        while pausa is not None:
            pausa = avanzar(app, cfg, Command(resume=responder(pausa)), emitir)
    except ErrorInfraestructura:                        # RetryPolicy ya agotó sus intentos: se escala, sin traceback
        return cortar(app, cfg, MOTIVO_INFRAESTRUCTURA)
    except GraphRecursionError:                         # un ciclo que no termina: se escala, sin traceback
        limite = cfg.get("recursion_limit", RECURSION_LIMIT)
        return cortar(app, cfg, f"se alcanzó el límite de {limite} pasos del grafo (posible ciclo sin salida)")
    return app.get_state(cfg).values


def cortar(app, cfg: dict, motivo: str) -> dict:
    """Estado de una corrida cortada por un fallo del propio flujo: ESCALAR con un motivo fijo.

    No se guarda en el checkpoint: el thread queda donde estaba y puede reanudarse con --reanudar. La clave `cortada`
    le avisa a main que debe escribir el reporte (el nodo reporte no llegó a correr).
    """
    valores = dict(app.get_state(cfg).values)
    thread = cfg["configurable"]["thread_id"]
    return {**valores, "estado_final": ESCALAR, "cortada": f"{motivo}. Para reanudar: --reanudar {thread}",
            "bitacora": [*valores.get("bitacora", []), f"ESCALAR · {motivo}"]}


def reanudar(app, cfg: dict, responder: Callable[[dict], str]) -> dict:
    """Reanuda un thread desde su checkpoint: responde la pausa pendiente o continúa el nodo que quedó a medias."""
    estado = app.get_state(cfg)
    pendientes = [i for tarea in estado.tasks for i in tarea.interrupts]
    if pendientes:
        entrada = Command(resume=responder(pendientes[0].value))
    elif estado.next:
        entrada = None                                  # se cortó a mitad de camino: sigue desde el checkpoint
    else:
        return estado.values                            # ya había terminado
    return correr(app, cfg, responder, entrada)


def responder_en_terminal(pausa: dict) -> str:
    """Muestra la pausa (preguntas o plan) y lee la respuesta de la persona con input()."""
    for clave in ("preguntas", "plan"):
        if clave in pausa:
            contenido = pausa[clave]
            print(f"\n--- {clave.upper()} ---\n" + ("\n".join(contenido) if isinstance(contenido, list) else contenido))
    return input(pausa["pregunta"] + ": ")


def responder_si(pausa: dict) -> str:
    """--aprobar: la persona aprueba por adelantado las dos pausas (preguntas y plan)."""
    return "si"


# --- Ensayo: dobles deterministas (sin modelo, sin Docker) ---------------------------------------------
@dataclass
class Escenario:
    """Qué debe pasar en un ensayo; cada campo fuerza una ruta del grafo."""

    sospechosa: bool = False                 # el filtro marca la historia como sospechosa
    defensas: bool = True                    # False = DEFENSAS=0
    motivo: str = "pide leer un archivo de credenciales"
    preguntas: list[str] = field(default_factory=list)      # preguntas abiertas que deja el analista
    construir_fallos: int = 0                # veces que la verificación de la app falla antes de pasar
    e2e_fallos: int = 0                      # veces que e2e falla antes de pasar (99 = nunca)
    responsable: str = "automatizador"       # a quién enruta el triage
    revisor_rechazos: int = 0                # veces que el revisor rechaza (capa LLM)
    revisor_estatico_rechaza: bool = False   # el revisor rechaza una vez en la capa estática (sin llamar al modelo)
    revisor_salida_invalida: bool = False    # la salida del revisor no valida contra Revision: debe escalar
    documentar_invalido: bool = False        # la salida del documentador no valida: debe escalar
    correccion_sin_cambios: bool = False     # el desarrollador «corrige» sin tocar app/ (la construcción inicial sí)
    infra_fallos: int = 0                    # veces que claude -p no responde (infraestructura) al correr infra_skill
    infra_skill: str = "/criterios"          # el skill cuya llamada falla por infraestructura
    infra_revisor_fallos: int = 0            # veces que la llamada del revisor falla por infraestructura
    app_falla_tras_correccion: bool = False  # la app no verifica después de corregir el código
    redespliegue_falla: bool = False         # el redespliegue falla después de corregir el código
    sin_artefacto: frozenset[str] = frozenset()   # skills que «terminan» sin escribir su artefacto


PRESETS = {
    "lista": Escenario(),
    "bloqueada": Escenario(sospechosa=True),
    "sin_defensas": Escenario(defensas=False),
    "preguntas": Escenario(preguntas=["¿Qué formato tiene el número de empleado?"]),
    "construir_reintento": Escenario(construir_fallos=1),
    "e2e_pruebas": Escenario(e2e_fallos=1, responsable="automatizador"),
    "e2e_codigo": Escenario(e2e_fallos=1, responsable="desarrollador"),
    "e2e_despliegue": Escenario(e2e_fallos=1, responsable="despliegue"),
    "escalar_e2e": Escenario(e2e_fallos=99),
    "revisor_rechaza": Escenario(revisor_rechazos=1),
    "revisor_estatico_rechaza": Escenario(revisor_estatico_rechaza=True),
    "revisor_salida_invalida": Escenario(revisor_salida_invalida=True),
    "documentar_invalido": Escenario(documentar_invalido=True),
    "infra_una_vez": Escenario(infra_fallos=1),
    "infra_agotada": Escenario(infra_fallos=99),
}

_GHERKIN = """# language: es
Característica: Registrar empleado

  Escenario: Registro exitoso
    Dado que estoy en el formulario de alta
    Cuando envío datos válidos
    Entonces el sistema asigna un número de empleado

  Escenario: Registro con correo duplicado
    Dado que el correo ya existe
    Cuando envío el formulario
    Entonces veo un error de correo duplicado
"""


class Ensayo:
    """Dobles falsos de `claude -p` y de las verificaciones: escriben artefactos válidos según el Escenario."""

    def __init__(self, salida: Path, escenario: Escenario):
        """Crea los dobles; `prompts`, `modelos` y `verificaciones` registran lo que el grafo les pidió."""
        self.salida, self.esc = salida, escenario
        self.app = salida.parent / "app"
        self.registros = salida.parent / "registros"
        self.prompts: list[str] = []
        self.modelos: list[str] = []
        self.verificaciones: list[str] = []
        self.bases: list[str] = []          # el commit base que el grafo le pasó al revisor en cada revisión
        self.documentaciones: list[str] = []    # el commit base de cada llamada al documentador
        self._fallos = {"app": 0, "e2e": 0, "revision": 0, "versiones": 0, "infra": 0, "infra_revisor": 0}

    def servicios(self) -> Servicios:
        """Los Servicios que usa el grafo, con el revisor y el documentador dobles."""
        return Servicios(ejecutar=self.ejecutar, verificar=self.verificar, salida=self.salida, app=self.app,
                         registros=self.registros, revisor=self.revisor, documentador=self.documentador)

    def _escribir(self, ruta: Path, texto: str) -> None:
        """Escribe un archivo garantizando que su mtime avance (el grafo lo compara)."""
        antes = ruta.stat().st_mtime_ns if ruta.exists() else 0
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
        nuevo = max(time.time_ns(), antes + 1_000_000_000)
        os.utime(ruta, ns=(nuevo, nuevo))

    def ejecutar(self, prompt: str, *, modelo: str, **_) -> dict:
        """Doble de claude.ejecutar: registra el prompt y deja el artefacto del skill (salvo `sin_artefacto`)."""
        self.prompts.append(prompt)
        self.modelos.append(modelo)
        skill = prompt.split()[0]
        if skill == self.esc.infra_skill and self._fallos["infra"] < self.esc.infra_fallos:
            self._fallos["infra"] += 1                  # lo que lanzaría claude.ejecutar_exigiendo sin respuesta
            raise ErrorInfraestructura("claude -p sin respuesta (simulado)")
        hu = re.search(r"HU-\d+", prompt).group()
        carpeta = self.salida / hu
        if skill not in self.esc.sin_artefacto:
            if skill == "/filtrar":
                self._escribir(carpeta / "veredicto.json", json.dumps(
                    {"sospechosa": self.esc.sospechosa, "motivo": self.esc.motivo}, ensure_ascii=False))
            elif skill == "/criterios":
                extra = "\n# Preguntas abiertas\n" + "".join(f"# - {p}\n" for p in self.esc.preguntas) \
                    if self.esc.preguntas else ""
                self._escribir(carpeta / "criterios.feature", _GHERKIN + extra)
            elif skill == "/casos":
                caso = {"nivel": "api", "precondiciones": [], "pasos": ["enviar"], "datos": {},
                        "resultado_esperado": "ok"}
                self._escribir(carpeta / "casos_prueba.json", json.dumps({"historia": hu, "casos": [
                    {"id": "CP-01", "escenario": "Registro exitoso", **caso},
                    {"id": "CP-02", "escenario": "Registro con correo duplicado", **caso}]}))
            elif skill == "/plan":
                self._escribir(carpeta / "plan.md", "# Plan\n- Backend: endpoint de alta\n"
                                                    "- Frontend: formulario con data-testid=\"form-alta\"\n")
            elif skill == "/construir" and not (self.esc.correccion_sin_cambios and "Corrige:" in prompt):
                self._fallos["versiones"] += 1
                self._escribir(self.app / "backend" / "main.py", f"# versión {self._fallos['versiones']}\n")
            elif skill == "/triage":
                self._escribir(carpeta / "diagnostico.json", json.dumps({
                    "responsable": self.esc.responsable, "causa": "la prueba espera 200 y el criterio dice 201",
                    "criterio": "Registro exitoso", "instruccion": "cambiar el código esperado a 201"}))
        return {"result": "ok", "structured_output": None, "total_cost_usd": 0.01, "duration_ms": 1,
                "is_error": False, "codigo_salida": 0}

    def verificar(self, nombre: str, hu: str | None = None) -> tuple[bool, str]:
        """Doble de verificacion.verificar: pasa o falla según el Escenario."""
        self.verificaciones.append(nombre)
        if nombre == "defensas":
            return True, "DEFENSAS ACTIVADAS" if self.esc.defensas else "DEFENSAS DESACTIVADAS (solo en clase)"
        if nombre == "app" and self.esc.app_falla_tras_correccion and self._fallos["e2e"] > 0:
            return False, "la app corregida no arranca: SyntaxError simulado"
        if nombre == "redespliegue" and self.esc.redespliegue_falla:
            return False, "docker compose up falló: puerto 8000 ocupado (simulado)"
        if nombre == "app" and self._fallos["app"] < self.esc.construir_fallos:
            self._fallos["app"] += 1
            return False, "el backend no arranca: ImportError simulado"
        if nombre == "e2e":
            if self._fallos["e2e"] < self.esc.e2e_fallos:
                self._fallos["e2e"] += 1
                log = "1 failed, 47 passed\n- tests.api.test_hu_01::test_cp_01\n  assert 201 == 200"
                self._escribir(self.salida / hu / "fallos.md", f"# Pruebas de {hu}\n\n{log}\n")
                return False, log
            return True, "48 passed"
        return True, "ok"

    def revisor(self, hu: str, base: str) -> ResultadoRevision:
        """Doble del revisor: según el Escenario escala, rechaza en la capa estática o en la LLM, y luego aprueba."""
        self.bases.append(base)
        if self._fallos["infra_revisor"] < self.esc.infra_revisor_fallos:
            self._fallos["infra_revisor"] += 1
            raise ErrorInfraestructura("claude -p sin respuesta (simulado)")
        if self.esc.revisor_salida_invalida:
            return ResultadoRevision("escalar", motivo="salida del revisor ausente o inválida", modelo_llamado=True,
                                     costo=0.01)
        if self.esc.revisor_estatico_rechaza and self._fallos["revision"] == 0:
            self._fallos["revision"] += 1
            return ResultadoRevision("rechazada", [Observacion(
                archivo="app/backend/main.py", categoria="seguridad", detalle="bandit B307: uso de eval (nuevos: 1)")])
        if self._fallos["revision"] < self.esc.revisor_rechazos:
            self._fallos["revision"] += 1
            return ResultadoRevision("rechazada", [Observacion(
                archivo="app/backend/main.py", categoria="regla_negocio",
                detalle="falta validar el correo en el backend")], modelo_llamado=True, costo=0.01)
        return ResultadoRevision("aprobada", modelo_llamado=True, costo=0.01)

    def documentador(self, hu: str, base: str) -> ResultadoDocumentacion:
        """Doble del documentador: deja un documento fijo, o escala con un motivo fijo si el Escenario lo pide."""
        self.documentaciones.append(base)
        if self.esc.documentar_invalido:
            return ResultadoDocumentacion(motivo="salida del documentador ausente o inválida", modelo_llamado=True,
                                          costo=0.01)
        return ResultadoDocumentacion(markdown=f"# Documentación · {hu}\n\n(documento de ensayo)\n",
                                      modelo_llamado=True, costo=0.01)


# --- CLI ---------------------------------------------------------------------------------------------
def resumen(valores: dict, sv: Servicios, thread_id: str) -> int:
    """Imprime el resultado de la corrida y devuelve el código de salida (0 solo si quedó LISTA)."""
    estado = valores.get("estado_final", "?")
    print(f"\n=== {valores.get('hu', '?')} · {estado} · {valores.get('costo_usd', 0.0):.4f} USD · "
          f"ciclos {valores.get('ciclos', 0)} · thread {thread_id} ===")
    for linea in valores.get("bitacora", []):
        print(" -", linea)
    print(f"Reporte: {sv.salida / valores.get('hu', '') / 'reporte.md'}")
    return 0 if estado == LISTA else 1


def historial(app, cfg: dict) -> list[str]:
    """Checkpoints de un thread, del más reciente al más antiguo: paso, siguiente nodo, checkpoint_id y hora. Solo lectura."""
    lineas = []
    for instantanea in app.get_state_history(cfg):
        paso = instantanea.metadata.get("step", "?")
        siguiente = ", ".join(instantanea.next) or "(fin)"
        hora = datetime.fromisoformat(instantanea.created_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        lineas.append(f"paso {paso:>3}  siguiente: {siguiente:<28}  checkpoint_id: "
                      f"{instantanea.config['configurable']['checkpoint_id']}  {hora}")
    return lineas


def mostrar_historial(thread_id: str) -> int:
    """--historial: abre salida/fabrica.sqlite en modo de solo lectura y lista los checkpoints del thread."""
    ruta = RAIZ / "salida" / "fabrica.sqlite"
    if not ruta.exists():
        print(f"No existe {ruta}: todavía no hay corridas.", file=sys.stderr)
        return 2
    conexion = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    try:
        lineas = historial(construir_grafo(servicios_reales(), SqliteSaver(conexion)), config_de(thread_id))
    finally:
        conexion.close()
    if not lineas:
        print(f"No hay checkpoints para el thread {thread_id}.", file=sys.stderr)
        return 2
    print(f"Historial de {thread_id} (del más reciente al más antiguo):", *lineas, sep="\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: python -m flujos.fabrica <historia> [--aprobar] [--ensayo] [--reanudar <thread_id>]."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")        # Windows usa cp1252 en pipes y archivos
    p = argparse.ArgumentParser(prog="python -m flujos.fabrica", description="La fábrica como grafo de LangGraph")
    p.add_argument("historia", nargs="?", help="ruta de la historia, por ejemplo historias/HU-01-registrar-empleado.md")
    p.add_argument("--aprobar", action="store_true", help="responde «si» por adelantado en las dos pausas humanas")
    p.add_argument("--ensayo", action="store_true", help="dobles deterministas: sin modelo y sin Docker")
    p.add_argument("--escenario", default="lista", choices=sorted(PRESETS), help="ruta a forzar en el ensayo")
    p.add_argument("--reanudar", metavar="THREAD_ID", help="reanuda un thread desde su checkpoint")
    p.add_argument("--diagrama", action="store_true", help="solo exporta docs/grafo.mmd")
    p.add_argument("--historial", metavar="THREAD_ID", help="lista los checkpoints de una corrida (solo lectura)")
    args = p.parse_args(argv)
    if args.historial:
        return mostrar_historial(args.historial)

    base = "ensayo"
    if args.historia and not args.ensayo and not args.reanudar and not args.diagrama:
        problema = precondicion_app()                   # precondición de una corrida real: app/ limpia en git
        problema = problema or precondicion_sandbox()   # y las imágenes del sandbox: falla antes de gastar tokens
        if problema:
            print(f"No se inicia la corrida. {problema}", file=sys.stderr)
            return 2
        base = commit_base()                            # lo que cambie desde este commit es lo que revisa el revisor

    if args.ensayo:                                     # el ensayo trabaja en una carpeta temporal: no toca salida/
        carpeta = Path(tempfile.mkdtemp(prefix="fabrica_ensayo_"))
        print(f"Ensayo «{args.escenario}» en {carpeta}")
        sv = Ensayo(carpeta / "salida", PRESETS[args.escenario]).servicios()
    else:
        sv = servicios_reales()
    sv.salida.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(sv.salida / "fabrica.sqlite", check_same_thread=False)   # las ramas corren en hilos
    app = construir_grafo(sv, SqliteSaver(conexion), espera_reintento=0.05 if args.ensayo else ESPERA_REINTENTO)
    if not args.ensayo:
        exportar_diagrama(app)
        exportar_diagrama_correccion(sv)
    if args.diagrama:
        print(f"Diagramas exportados en {RAIZ / 'docs' / 'grafo.mmd'} y {RAIZ / 'docs' / 'grafo-correccion.mmd'}")
        return 0
    responder = responder_si if args.aprobar else responder_en_terminal
    try:
        if args.reanudar:
            thread_id = args.reanudar
            print(f"thread_id: {thread_id}  (reanudando)")
            valores = reanudar(app, config_de(thread_id), responder)
        elif args.historia:
            entrada = estado_inicial(args.historia, base)
            thread_id = nuevo_thread(entrada["hu"])
            print(f"thread_id: {thread_id}  (para reanudar: --reanudar {thread_id})")
            valores = correr(app, config_de(thread_id), responder, entrada)
        else:
            p.error("indica una historia o --reanudar")
        if valores.get("cortada"):                      # la corrida no llegó al nodo reporte: se escribe aquí
            nodo_reporte(sv, valores)
            print(f"CORRIDA CORTADA: {valores['cortada']}", file=sys.stderr)
    finally:
        conexion.close()
    return resumen(valores, sv, thread_id)


if __name__ == "__main__":
    sys.exit(main())
