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
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

import verificacion
from flujos import claude
from validadores.contratos import Diagnostico, preguntas_abiertas
from validadores.validar import problemas_de

RAIZ = Path(__file__).resolve().parent.parent

# --- Topes: todo bucle tiene un límite -----------------------------------------------------------
MAX_RECHAZOS = 2             # el plan se puede rechazar 2 veces; el 3.º rechazo escala a una persona
MAX_INTENTOS_CONSTRUIR = 2   # la construcción y un reintento con el log
MAX_CICLOS = 2               # ciclos triage → corrección → e2e
MAX_CICLOS_REVISION = 1      # fase 2: si el revisor rechaza, un solo ciclo de corrección

# Estados finales posibles (los mismos cuatro que el reporte de /fabrica)
LISTA = "LISTA"
BLOQUEADA = "BLOQUEADA POR SEGURIDAD"
DETENIDA = "DETENIDA POR LA PERSONA"
ESCALAR = "ESCALAR A UNA PERSONA"

# Cada llamada fija su modelo: nada se hereda de la sesión
MODELOS = {
    "filtrar": "haiku", "criterios": "sonnet", "casos": "sonnet", "plan": "sonnet",
    "construir": "sonnet", "desplegar": "sonnet", "automatizar": "sonnet", "triage": "sonnet",
}


class Estado(TypedDict, total=False):
    """Estado del grafo. Los campos con reducer se acumulan; el resto se sobrescribe."""

    historia: str                    # ruta de la historia; el orquestador NUNCA lee su contenido
    hu: str                          # HU-xx, sale del nombre del archivo
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
    ciclos: int                      # ciclos de corrección por e2e
    responsable: str
    instruccion: str                 # qué debe corregir el responsable (diagnóstico del triage u observaciones)
    revisiones: int                  # ciclos de corrección por rechazo del revisor
    revision_ok: bool
    estado_final: str
    costo_usd: Annotated[float, operator.add]
    bitacora: Annotated[list[str], operator.add]
    eventos_seguridad: Annotated[list[dict], operator.add]


# --- Servicios: lo que el grafo necesita del mundo (se sustituye en el ensayo) -----------------------
def revisor_pendiente(hu: str) -> tuple[bool, list[str]]:
    """Revisor de la fase 1: un STUB que aprueba siempre. La fase 2 lo reemplaza por un revisor con modelo."""
    return True, []


@dataclass
class Servicios:
    """Dependencias externas del grafo: llamar al modelo, verificar y dónde se escribe `salida/`."""

    ejecutar: Callable[..., dict]                               # (prompt, *, modelo) -> dict de claude.ejecutar
    verificar: Callable[[str, str | None], tuple[bool, str]]    # (nombre, hu) -> (ok, log), como verificacion
    salida: Path
    revisor: Callable[[str], tuple[bool, list[str]]] = revisor_pendiente


def servicios_reales() -> Servicios:
    """Servicios de verdad: `claude -p`, las verificaciones de verificacion/ y la carpeta salida/ del proyecto."""
    return Servicios(ejecutar=claude.ejecutar, verificar=verificacion.verificar, salida=RAIZ / "salida")


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


def registrar_seguridad(sv: Servicios, hu: str, eventos: list[dict]) -> list[dict]:
    """Agrega los eventos a salida/seguridad.jsonl SIEMPRE (también con DEFENSAS=0) y los devuelve."""
    completos = [{"ts": round(time.time(), 1), "hu": hu, **e} for e in eventos]
    sv.salida.mkdir(parents=True, exist_ok=True)
    with open(sv.salida / "seguridad.jsonl", "a", encoding="utf-8") as f:
        f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in completos)
    return completos


def ultimas_lineas(texto: str, n: int = 40) -> str:
    """Las últimas n líneas de un log, para pasarlas a un agente sin inundarlo."""
    return "\n".join(texto.splitlines()[-n:])


# --- Nodos -------------------------------------------------------------------------------------------
def nodo_filtrar(sv: Servicios, s: Estado) -> dict:
    """Filtro de seguridad: /filtrar → veredicto.json. Solo el booleano `sospechosa` entra al flujo.

    El motivo del veredicto va únicamente a `eventos_seguridad` (seguridad.jsonl y el reporte): nunca a un prompt.
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
    if problemas:                                   # sin veredicto válido no se avanza: falla cerrado
        eventos.append({"evento": "veredicto_invalido", "problemas": problemas})
        return {**falla("Filtro de seguridad", problemas, costo),
                "eventos_seguridad": registrar_seguridad(sv, hu, eventos)}
    veredicto = json.loads(ruta.read_text(encoding="utf-8"))
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
    """Desarrollador: /construir; la verificación de la app decide. Si falla, un reintento con el log.

    OJO, intencional: el subagente desarrollador ya tiene su propia compuerta (SubagentStop, máx 2), así que con
    el reintento del grafo son hasta 3 intentos de corregir antes de escalar.
    """
    hu = s["hu"]
    intentos = s.get("intentos", 0)
    correccion = ""
    if intentos > 0:
        correccion = f" La verificación falló; corrige esto:\n{ultimas_lineas(s.get('log_app', ''))}"
    respuesta = sv.ejecutar(f"/construir {hu}{correccion}", modelo=MODELOS["construir"])
    ok, log = sv.verificar("app", hu)               # el código decide, no el agente
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
        return Command(update=falla("Triage", problemas, costo), goto="reporte")
    d = Diagnostico.model_validate_json(ruta.read_text(encoding="utf-8"))
    destino = {"desarrollador": "corregir_codigo", "automatizador": "corregir_pruebas",
               "despliegue": "corregir_despliegue"}[d.responsable]
    return Command(update={"responsable": d.responsable, "instruccion": f"{d.causa}\n{d.instruccion}",
                           "ciclos": s.get("ciclos", 0) + 1, "costo_usd": costo,
                           "bitacora": [f"Triage → {d.responsable}: {d.causa}"]},
                   goto=destino)


def nodo_corregir_codigo(sv: Servicios, s: Estado) -> dict:
    """Corrige el código: /construir con la instrucción del diagnóstico, y reconstruye los contenedores."""
    hu = s["hu"]
    respuesta = sv.ejecutar(f"/construir {hu} Corrige: {s['instruccion']}", modelo=MODELOS["construir"])
    ok, _ = sv.verificar("redespliegue", hu)        # el código cambió: los contenedores tienen la versión vieja
    return {"costo_usd": costo_de(respuesta), "bitacora": [f"Código corregido; redespliegue {'OK' if ok else 'FALLA'}"]}


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
    """Revisión de resultados, AL FINAL (después de e2e OK). En la fase 1 el revisor es un STUB que aprueba.

    Fase 2: si el revisor rechaza → corregir_codigo → redespliegue → e2e → revisar, con un máximo de
    MAX_CICLOS_REVISION ciclos; al agotarlo se escala.
    """
    aprobado, observaciones = sv.revisor(s["hu"])
    pendiente = sv.revisor is revisor_pendiente
    if aprobado:
        return {"revision_ok": True,
                "bitacora": ["Revisión: aprobada (revisor pendiente: fase 2)" if pendiente else "Revisión: aprobada"]}
    revisiones = s.get("revisiones", 0)
    if revisiones >= MAX_CICLOS_REVISION:
        return {"revision_ok": False, "estado_final": ESCALAR,
                "bitacora": ["Revisión: el revisor sigue rechazando tras el ciclo de corrección: ESCALAR"]}
    return {"revision_ok": False, "revisiones": revisiones + 1,
            "instruccion": "Observaciones del revisor:\n- " + "\n- ".join(observaciones),
            "bitacora": [f"Revisión: rechazada ({len(observaciones)} observaciones)"]}


def nodo_reporte(sv: Servicios, s: Estado) -> dict:
    """Escribe salida/HU-xx/reporte.md: estado, ciclos, costo, seguridad, bitácora y último log de e2e."""
    estado = s.get("estado_final") or (LISTA if s.get("e2e_ok") and s.get("revision_ok") else ESCALAR)
    carpeta = sv.salida / s["hu"]
    carpeta.mkdir(parents=True, exist_ok=True)
    lineas = [f"# Reporte · {s['hu']}", "", f"**Estado:** {estado}",
              f"**Ciclos de corrección:** {s.get('ciclos', 0)} (revisión: {s.get('revisiones', 0)})",
              f"**Costo de agentes:** {s.get('costo_usd', 0.0):.4f} USD", "", "## Seguridad"]
    eventos = s.get("eventos_seguridad", [])
    lineas += [f"- {json.dumps(e, ensure_ascii=False)}" for e in eventos] or ["- sin eventos"]
    lineas += ["", "## Bitácora", *[f"- {b}" for b in s.get("bitacora", [])],
               "", "## Última ejecución de pruebas", "```", s.get("log_e2e", "(no se ejecutaron)"), "```", ""]
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
    """e2e OK → revisar; falla con ciclos disponibles → triage; sin ciclos → reporte."""
    if s.get("estado_final"):
        return "reporte"
    return "revisar" if s.get("e2e_ok") else "triage"


def tras_revisar(s: Estado) -> str:
    """Revisión aprobada o estado final → reporte; rechazada con ciclo disponible → corregir el código."""
    if s.get("estado_final") or s.get("revision_ok"):
        return "reporte"
    return "corregir_codigo"


# --- Grafo -------------------------------------------------------------------------------------------
def construir_grafo(sv: Servicios, checkpointer) -> CompiledStateGraph:
    """Arma y compila el grafo de la fábrica con los servicios dados y un checkpointer (SqliteSaver)."""
    g = StateGraph(Estado)
    nodos = {"filtrar": nodo_filtrar, "analizar": nodo_analizar, "preguntas": nodo_preguntas,
             "disenar": nodo_disenar, "planificar": nodo_planificar, "aprobar_plan": nodo_aprobar_plan,
             "construir": nodo_construir, "desplegar": nodo_desplegar, "automatizar": nodo_automatizar,
             "listo": nodo_listo, "e2e": nodo_e2e, "corregir_codigo": nodo_corregir_codigo,
             "corregir_pruebas": nodo_corregir_pruebas, "corregir_despliegue": nodo_corregir_despliegue,
             "revisar": nodo_revisar, "reporte": nodo_reporte}
    for nombre, fn in nodos.items():
        g.add_node(nombre, lambda s, fn=fn: fn(sv, s))
    g.add_node("triage", lambda s: nodo_triage(sv, s),
               destinations=("corregir_codigo", "corregir_pruebas", "corregir_despliegue", "reporte"))

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
    g.add_conditional_edges("e2e", tras_e2e, ["revisar", "triage", "reporte"])
    for correccion in ("corregir_codigo", "corregir_pruebas", "corregir_despliegue"):
        g.add_edge(correccion, "e2e")                                   # el ciclo: corregir y volver a probar
    g.add_conditional_edges("revisar", tras_revisar, ["corregir_codigo", "reporte"])
    g.add_edge("reporte", END)
    return g.compile(checkpointer=checkpointer)


def exportar_diagrama(app, ruta: Path = RAIZ / "docs" / "grafo.mmd") -> Path:
    """Guarda el grafo como Mermaid (get_graph().draw_mermaid()) en docs/grafo.mmd."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(app.get_graph().draw_mermaid(), encoding="utf-8")
    return ruta


# --- Ejecución con pausas humanas --------------------------------------------------------------------
def estado_inicial(historia: str) -> Estado:
    """Estado de partida: la ruta y el HU-xx salen del NOMBRE del archivo (nunca se lee su contenido)."""
    hu = re.search(r"HU-\d+", Path(historia).name)
    if not hu:
        raise ValueError(f"El nombre de la historia debe contener HU-xx: {historia}")
    return {"historia": historia, "hu": hu.group(), "rechazos": 0, "intentos": 0, "ciclos": 0, "revisiones": 0,
            "costo_usd": 0.0, "bitacora": [], "eventos_seguridad": []}


def nuevo_thread(hu: str) -> str:
    """thread_id único por corrida (HU-xx-AAAAMMDD-HHMMSS): evita arrastrar contadores de una corrida anterior."""
    return f"{hu}-{datetime.now():%Y%m%d-%H%M%S}"


def correr(app, cfg: dict, responder: Callable[[dict], str], entrada=None) -> dict:
    """Avanza el grafo y atiende cada pausa humana con `responder(pausa) -> texto` y Command(resume=...)."""
    salida = app.invoke(entrada, cfg)
    while "__interrupt__" in salida:
        pausa = salida["__interrupt__"][0].value
        salida = app.invoke(Command(resume=responder(pausa)), cfg)
    return app.get_state(cfg).values


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
    revisor_rechazos: int = 0                # veces que el revisor (fase 2) rechaza
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
        self.prompts: list[str] = []
        self.modelos: list[str] = []
        self.verificaciones: list[str] = []
        self._fallos = {"app": 0, "e2e": 0, "revision": 0}

    def servicios(self) -> Servicios:
        """Los Servicios que usa el grafo; sin rechazos forzados se usa el STUB real `revisor_pendiente`."""
        revisor = self.revisor if self.esc.revisor_rechazos else revisor_pendiente
        return Servicios(ejecutar=self.ejecutar, verificar=self.verificar, salida=self.salida, revisor=revisor)

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

    def revisor(self, hu: str) -> tuple[bool, list[str]]:
        """Doble del revisor de la fase 2: rechaza `revisor_rechazos` veces y luego aprueba."""
        if self._fallos["revision"] < self.esc.revisor_rechazos:
            self._fallos["revision"] += 1
            return False, ["falta validar el correo en el backend"]
        return True, []


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
    args = p.parse_args(argv)

    if args.ensayo:                                     # el ensayo trabaja en una carpeta temporal: no toca salida/
        carpeta = Path(tempfile.mkdtemp(prefix="fabrica_ensayo_"))
        print(f"Ensayo «{args.escenario}» en {carpeta}")
        sv = Ensayo(carpeta, PRESETS[args.escenario]).servicios()
    else:
        sv = servicios_reales()
    sv.salida.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(sv.salida / "fabrica.sqlite", check_same_thread=False)   # las ramas corren en hilos
    app = construir_grafo(sv, SqliteSaver(conexion))
    if not args.ensayo:
        exportar_diagrama(app)
    if args.diagrama:
        print(f"Diagrama exportado en {RAIZ / 'docs' / 'grafo.mmd'}")
        return 0
    responder = responder_si if args.aprobar else responder_en_terminal
    try:
        if args.reanudar:
            thread_id = args.reanudar
            valores = reanudar(app, {"configurable": {"thread_id": thread_id}}, responder)
        elif args.historia:
            entrada = estado_inicial(args.historia)
            thread_id = nuevo_thread(entrada["hu"])
            print(f"thread_id: {thread_id}  (para reanudar: --reanudar {thread_id})")
            valores = correr(app, {"configurable": {"thread_id": thread_id}}, responder, entrada)
        else:
            p.error("indica una historia o --reanudar")
    finally:
        conexion.close()
    return resumen(valores, sv, thread_id)


if __name__ == "__main__":
    sys.exit(main())
