"""Fase 4 del reto: el filtro de seguridad en lote, en paralelo con `Send`.

Pasa VARIAS historias por el filtro de seguridad a la vez y junta los veredictos. NO construye nada: solo dice qué
historias están listas para la fábrica (`python -m flujos.fabrica <historia>`). Solo el filtro va en paralelo: cada
historia escribe en su propia carpeta (`salida/HU-xx/`, `registros/HU-xx/`), mientras que `app/`, el despliegue y el
commit base son compartidos y no admiten dos corridas a la vez.

Uso:
    python -m flujos.lote historias/HU-01-registrar-empleado.md historias/HU-99-envenenada.md
    python -m flujos.lote --todas [--ensayo]       (--ensayo: dobles deterministas, sin modelo)
    python -m flujos.lote --diagrama               (solo exporta docs/grafo-lote.mmd)
"""
import argparse
import json
import operator
import re
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from flujos.claude import ErrorInfraestructura
from flujos.fabrica import (
    BLOQUEADA,
    ESPERA_REINTENTO,
    RAIZ,
    Servicios,
    estado_inicial,
    nodo_filtrar,
    politica_de_reintento,
    servicios_reales,
)

MAX_CONCURRENCIA = 4        # ramas del filtro que corren a la vez
OK, BLOQUEADA_L, FALLA, SIN_FILTRAR = "ok", "bloqueada", "falla", "sin_filtrar"


class EstadoLote(TypedDict, total=False):
    """Estado del lote. Los campos con reducer reciben lo que devuelve cada rama sin pisarse."""

    historias: list[str]
    resultados: Annotated[list[dict], operator.add]     # {"hu", "historia", "estado"[, "error"]}: nunca el motivo
    costo_usd: Annotated[float, operator.add]
    bitacora: Annotated[list[str], operator.add]


def _hu_de(historia: str) -> str:
    """HU-xx del nombre del archivo, o «?» si no lo trae (solo para etiquetar un error)."""
    m = re.search(r"HU-\d+", Path(historia).name)
    return m.group() if m else "?"


def estado_de(actualizacion: dict) -> str:
    """Traduce lo que devolvió `nodo_filtrar` a «ok», «bloqueada», «falla» o «sin_filtrar» (DEFENSAS=0).

    Mira solo datos públicos del resultado: nunca el motivo del veredicto.
    """
    if any(e.get("evento") == "filtro_omitido" for e in actualizacion.get("eventos_seguridad", [])):
        return SIN_FILTRAR
    final = actualizacion.get("estado_final")
    if final == BLOQUEADA:
        return BLOQUEADA_L
    if final or actualizacion.get("sospechosa") is not False:
        return FALLA            # ESCALAR (veredicto ausente o inválido) o sin veredicto: falla cerrado
    return OK


# --- Entrada -------------------------------------------------------------------------------------------
def todas_las_historias(raiz: Path = RAIZ) -> list[str]:
    """Todas las historias/HU-*.md (sin backlog.md), ordenadas, como rutas relativas a la raíz."""
    return [p.relative_to(raiz).as_posix() for p in sorted((raiz / "historias").glob("HU-*.md"))]


def validar_historias(rutas: list[str], raiz: Path = RAIZ) -> tuple[list[str], str | None]:
    """Valida las rutas de entrada. Devuelve (rutas normalizadas relativas a la raíz, mensaje de error o None).

    Rechaza: lista vacía, archivos inexistentes o fuera de historias/, nombres sin HU-xx, backlog.md y duplicados
    (por archivo o por HU).
    """
    if not rutas:
        return [], "No hay historias: indica rutas o usa --todas."
    carpeta = (raiz / "historias").resolve()
    normalizadas: list[str] = []
    vistos: set[str] = set()
    for ruta in rutas:
        p = Path(ruta)
        real = (p if p.is_absolute() else Path.cwd() / p).resolve()
        if real.parent != carpeta:
            return [], f"La historia debe estar directamente en historias/: {ruta}"
        if not real.is_file():
            return [], f"No existe la historia: {ruta}"
        if real.name == "backlog.md" or not re.search(r"HU-\d+", real.name):
            return [], f"No es una historia HU-xx: {ruta}"
        hu = _hu_de(real.name)
        if hu in vistos:
            return [], f"Historia duplicada ({hu}): {ruta}"
        vistos.add(hu)
        normalizadas.append(real.relative_to(raiz.resolve()).as_posix())
    return normalizadas, None


# --- Grafo -------------------------------------------------------------------------------------------
def repartir(estado: EstadoLote) -> list[Send]:
    """Arista condicional desde START: una rama `filtrar_una` por historia (map)."""
    return [Send("filtrar_una", {"historia": h}) for h in estado["historias"]]


def _filtrar_con_reintento(sv: Servicios, historia: str, espera: float) -> dict:
    """Corre `nodo_filtrar` con los mismos 2 intentos y la misma espera que la fábrica, solo ante ErrorInfraestructura.

    Se reintenta aquí porque la excepción se atrapa dentro del nodo y la RetryPolicy de LangGraph nunca la vería.
    Un veredicto inválido NO se reintenta (nodo_filtrar ya lo devuelve como ESCALAR).
    """
    intentos = politica_de_reintento(espera).max_attempts
    for intento in range(1, intentos + 1):
        try:
            return nodo_filtrar(sv, estado_inicial(historia))
        except ErrorInfraestructura:
            if intento == intentos:
                raise
            time.sleep(espera)
    raise AssertionError("inalcanzable")


def construir_lote(sv: Servicios, checkpointer, espera: float = ESPERA_REINTENTO) -> CompiledStateGraph:
    """Arma el grafo del lote: START → (Send) filtrar_una × N → reunir → END."""

    def filtrar_una(entrada: dict) -> dict:
        """Una rama: filtra una historia con la lógica real de la fábrica. Falla cerrado, sin tumbar a las demás."""
        historia, hu = entrada["historia"], _hu_de(entrada["historia"])
        try:
            final = _filtrar_con_reintento(sv, historia, espera)
        except Exception as e:                 # la rama falla cerrado; solo se guarda el TIPO
            nombre = type(e).__name__
            print(f"{hu}: falla por {nombre}", file=sys.stderr)
            return {"resultados": [{"hu": hu, "historia": historia, "estado": FALLA, "error": nombre}],
                    "bitacora": [f"{hu}: {FALLA} ({nombre})"]}
        estado = estado_de(final)
        return {"resultados": [{"hu": hu, "historia": historia, "estado": estado}],
                "costo_usd": float(final.get("costo_usd", 0.0)), "bitacora": [f"{hu}: {estado}"]}

    def reunir(estado: EstadoLote) -> dict:
        """Nodo de unión: corre una vez, cuando terminaron todas las ramas. Anota solo conteos."""
        conteo: dict[str, int] = {}
        for r in estado.get("resultados", []):
            conteo[r["estado"]] = conteo.get(r["estado"], 0) + 1
        return {"bitacora": ["Lote: " + ", ".join(f"{n} {e}" for e, n in sorted(conteo.items()))]}

    g = StateGraph(EstadoLote)
    g.add_node("filtrar_una", filtrar_una)
    g.add_node("reunir", reunir)
    g.add_conditional_edges(START, repartir, ["filtrar_una"])
    g.add_edge("filtrar_una", "reunir")
    g.add_edge("reunir", END)
    return g.compile(checkpointer=checkpointer)


def config_lote(thread_id: str) -> dict:
    """El config de una corrida del lote: su thread y `max_concurrency` ramas a la vez."""
    return {"configurable": {"thread_id": thread_id}, "max_concurrency": MAX_CONCURRENCIA}


def nuevo_thread_lote(ahora: datetime | None = None) -> str:
    """thread_id del lote: «lote-AAAAMMDD-HHMMSS»."""
    return f"lote-{(ahora or datetime.now()):%Y%m%d-%H%M%S}"


# --- Reporte -----------------------------------------------------------------------------------------
def reporte_md(resultados: list[dict], costo: float, sello: str) -> str:
    """Markdown del lote: tabla HU | estado (ordenada por HU), costo total y el comando de cada historia «ok».

    Solo usa campos públicos de los resultados: el motivo del veredicto nunca llega aquí.
    """
    ordenados = sorted(resultados, key=lambda r: r["hu"])
    lineas = [f"# Filtro de seguridad en lote · {sello}", "", "| HU | estado |", "|---|---|"]
    for r in ordenados:
        detalle = f" ({r['error']})" if r.get("error") else ""
        lineas.append(f"| {r['hu']} | {r['estado']}{detalle} |")
    lineas += ["", f"Costo total: {costo:.4f} USD", ""]
    listas = [r for r in ordenados if r["estado"] == OK]
    if listas:
        lineas += ["## Listas para la fábrica", ""]
        lineas += [f"- {r['hu']}: `python -m flujos.fabrica {r['historia']}`" for r in listas]
    else:
        lineas.append("Ninguna historia está lista para la fábrica.")
    return "\n".join(lineas) + "\n"


def escribir_reporte(salida: Path, resultados: list[dict], costo: float, sello: str | None = None) -> Path:
    """Escribe salida/lote-AAAAMMDD-HHMMSS.md y devuelve su ruta."""
    sello = sello or f"{datetime.now():%Y%m%d-%H%M%S}"
    ruta = salida / f"lote-{sello}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(reporte_md(resultados, costo, sello), encoding="utf-8")
    return ruta


def exportar_diagrama_lote(sv: Servicios) -> Path:
    """Exporta el grafo del lote a docs/grafo-lote.mmd (Mermaid)."""
    ruta = RAIZ / "docs" / "grafo-lote.mmd"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(construir_lote(sv, None).get_graph().draw_mermaid(), encoding="utf-8")
    return ruta


# --- Ensayo ------------------------------------------------------------------------------------------
MOTIVO_ENSAYO = "MOTIVO-CENTINELA-NO-DEBE-SALIR"     # lo escribe el doble; las pruebas verifican que no se filtra


class EnsayoLote:
    """Dobles de `claude -p` y de `verificar`: `nodo_filtrar` corre su lógica real sobre ellos (como el Ensayo de la fábrica).

    Por el nombre de la historia: «99» → sospechosa; «invalida» → no deja veredicto (falla). Opcionales: `infra`
    (HU → fallos de infraestructura antes de responder) y `explotan` (HUs cuyo doble lanza ValueError).
    """

    def __init__(self, salida: Path, infra: dict[str, int] | None = None, explotan: set[str] | None = None,
                 defensas: bool = True):
        """Crea los dobles; `llamadas` registra el HU de cada llamada a `ejecutar` (seguro entre hilos)."""
        self.salida, self.registros, self.app = salida, salida.parent / "registros", salida.parent / "app"
        self.infra, self.explotan, self.defensas = dict(infra or {}), set(explotan or ()), defensas
        self.llamadas: list[str] = []
        self._fallos: dict[str, int] = {}
        self._lock = threading.Lock()

    def servicios(self) -> Servicios:
        """Los Servicios del lote; revisor y documentador no se usan y fallan si alguien los llama."""
        def nunca(*_, **__):
            raise AssertionError("el lote solo filtra")
        return Servicios(ejecutar=self.ejecutar, verificar=self.verificar, salida=self.salida, app=self.app,
                         registros=self.registros, revisor=nunca, documentador=nunca)

    def ejecutar(self, prompt: str, *, modelo: str, **_) -> dict:
        """Doble de claude.ejecutar para `/filtrar <historia>`: escribe salida/HU-xx/veredicto.json."""
        historia = prompt.split(maxsplit=1)[1]
        hu, nombre = _hu_de(historia), Path(historia).name
        with self._lock:
            self.llamadas.append(hu)
            hechos = self._fallos.get(hu, 0)
            falla_infra = hechos < self.infra.get(hu, 0)
            if falla_infra:
                self._fallos[hu] = hechos + 1
        if hu in self.explotan:
            raise ValueError("fallo inesperado del doble (este texto no debe salir)")
        if falla_infra:
            raise ErrorInfraestructura("claude -p sin respuesta (simulado)")
        if "invalida" not in nombre:
            ruta = self.salida / hu / "veredicto.json"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps({"sospechosa": "99" in nombre, "motivo": MOTIVO_ENSAYO}), encoding="utf-8")
        return {"result": "ok", "total_cost_usd": 0.01, "is_error": False}

    def verificar(self, nombre: str, hu: str | None = None) -> tuple[bool, str]:
        """Doble de verificacion.verificar: solo conoce «defensas»."""
        if nombre == "defensas":
            return True, "DEFENSAS ACTIVADAS" if self.defensas else "DEFENSAS DESACTIVADAS (solo en clase)"
        return True, ""


# --- CLI ---------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Exit 0 solo si todas las historias salen «ok»; 2 si la entrada no es válida."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m flujos.lote",
                                description="Filtro de seguridad en lote (paralelo, con Send). No construye nada.")
    p.add_argument("historias", nargs="*", help="rutas dentro de historias/")
    p.add_argument("--todas", action="store_true", help="todas las historias/HU-*.md (sin backlog.md)")
    p.add_argument("--ensayo", action="store_true", help="dobles deterministas: sin modelo")
    p.add_argument("--diagrama", action="store_true", help="solo exporta docs/grafo-lote.mmd")
    args = p.parse_args(argv)

    if args.diagrama:
        print(f"Diagrama exportado en {exportar_diagrama_lote(servicios_reales())}")
        return 0
    if args.todas and args.historias:
        print("Usa rutas o --todas, no ambas.", file=sys.stderr)
        return 2
    rutas, problema = validar_historias(todas_las_historias() if args.todas else args.historias)
    if problema:
        print(problema, file=sys.stderr)
        return 2

    if args.ensayo:
        carpeta = Path(tempfile.mkdtemp(prefix="lote_ensayo_"))
        print(f"Ensayo del lote en {carpeta}")
        sv, espera = EnsayoLote(carpeta / "salida").servicios(), 0.05
    else:
        sv, espera = servicios_reales(), ESPERA_REINTENTO
    sv.salida.mkdir(parents=True, exist_ok=True)
    thread_id = nuevo_thread_lote()
    print(f"thread_id: {thread_id}")
    conexion = sqlite3.connect(sv.salida / "lote.sqlite", check_same_thread=False)    # las ramas corren en hilos
    try:
        app = construir_lote(sv, SqliteSaver(conexion), espera)
        valores = app.invoke({"historias": rutas, "resultados": [], "costo_usd": 0.0, "bitacora": []},
                             config_lote(thread_id))
    finally:
        conexion.close()
    resultados, costo = valores["resultados"], valores["costo_usd"]
    ruta = escribir_reporte(sv.salida, resultados, costo, thread_id.removeprefix("lote-"))
    for r in sorted(resultados, key=lambda r: r["hu"]):
        print(f" - {r['hu']}: {r['estado']}" + (f" ({r['error']})" if r.get("error") else ""))
    print(f"Costo: {costo:.4f} USD · Reporte: {ruta}")
    return 0 if resultados and all(r["estado"] == OK for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
