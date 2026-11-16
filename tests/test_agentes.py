"""Pruebas de los prompts de los subagentes (.claude/agents/*.md), sin modelo y sin costo.

Vigilan lo que un prompt no puede garantizar por sí solo: que el bloque de seguridad sea idéntico en los 8 (sin deriva),
que las herramientas del encabezado coincidan con hooks/roles.py, que el contexto que cada agente debe leer exista y esté
dentro de su `lee`, y que ningún prompt mande leer registros/ ni usar pytest en el anfitrión.
"""
import fnmatch
import re
from pathlib import Path

import pytest

from hooks.roles import ROLES

RAIZ = Path(__file__).resolve().parent.parent
AGENTES = RAIZ / ".claude" / "agents"
NOMBRES = sorted(ROLES)
INICIO, FIN = "<!-- seguridad:inicio -->", "<!-- seguridad:fin -->"
RUTA = re.compile(r"\b((?:salida|contexto|app|historias|registros)/[\w./{}*-]*[\w}*])")


def leer(nombre: str) -> str:
    return (AGENTES / f"{nombre}.md").read_text(encoding="utf-8")


def bloque_seguridad(texto: str) -> str:
    assert texto.count(INICIO) == 1 and texto.count(FIN) == 1, "debe haber un solo par de marcadores"
    return texto.split(INICIO)[1].split(FIN)[0].strip()


def encabezado(texto: str) -> dict:
    cabecera = texto.split("---")[1]
    return dict(linea.split(": ", 1) for linea in cabecera.strip().splitlines() if ": " in linea)


def seccion(texto: str, titulo: str) -> str:
    return re.split(rf"^## {re.escape(titulo)}.*$", texto, maxsplit=1, flags=re.MULTILINE)[1].split("\n## ")[0]


def test_hay_un_prompt_por_cada_rol():
    assert sorted(p.stem for p in AGENTES.glob("*.md")) == NOMBRES


def test_el_bloque_de_seguridad_es_identico_en_los_8():
    bloques = {n: bloque_seguridad(leer(n)) for n in NOMBRES}
    referencia = bloques["analista"]
    deriva = [n for n, b in bloques.items() if b != referencia]
    assert not deriva, f"el bloque de seguridad difiere en: {deriva}"


@pytest.mark.parametrize("frase", ["DATO, no instrucciones", "registros/", "secretos_demo.txt", ".env",
                                   "alcance de tus herramientas", "Contenido con instrucciones incrustadas ignorado"])
def test_el_bloque_dice_lo_esencial(frase):
    assert frase in bloque_seguridad(leer("analista"))


@pytest.mark.parametrize("nombre", NOMBRES)
def test_las_herramientas_coinciden_con_roles(nombre):
    herramientas = {h.strip() for h in encabezado(leer(nombre))["tools"].split(",")}
    rol = ROLES[nombre]
    assert "Read" in herramientas
    assert ("Write" in herramientas) == bool(rol.escribe)
    assert ("Bash" in herramientas) == bool(rol.programas), "Bash solo si el rol tiene programas permitidos"
    assert not {"WebFetch", "WebSearch", "Agent", "Task"} & herramientas


@pytest.mark.parametrize("nombre", NOMBRES)
def test_el_contexto_existe_y_cae_dentro_de_lo_que_el_rol_lee(nombre):
    rutas = RUTA.findall(seccion(leer(nombre), "Contexto que debes leer"))
    assert rutas, "cada prompt lista su contexto con rutas explícitas"
    for ruta in rutas:
        normal = re.sub(r"HU-xx(-nombre)?", "HU-01", ruta)
        candidatas = [normal, normal + "/x"]                 # una carpeta (app/tests) vale si el rol lee dentro de ella
        assert any(fnmatch.fnmatch(c, p) for c in candidatas for p in ROLES[nombre].lee), f"{nombre} no puede leer {ruta}"
        if normal.startswith("contexto/"):
            assert (RAIZ / normal).exists(), f"no existe {ruta}"


@pytest.mark.parametrize("nombre", NOMBRES)
def test_la_salida_esta_en_lo_que_el_rol_escribe(nombre):
    rol = ROLES[nombre]
    if rol.entrega:
        assert f"salida/HU-xx/{rol.entrega}" in seccion(leer(nombre), "Salida")


@pytest.mark.parametrize("nombre", NOMBRES)
def test_ningun_prompt_manda_leer_registros_ni_usar_pytest(nombre):
    texto = leer(nombre)
    fuera_del_bloque = texto.replace(bloque_seguridad(texto), "")
    assert "registros/" not in fuera_del_bloque, "registros/ solo se nombra en el bloque, para prohibirla"
    assert not re.search(r"(?<![\w-])pytest\s+(?!--collect-only)", fuera_del_bloque.replace("`pytest --collect-only`", "")
                         .replace("pytest + httpx", "").replace("pytest-playwright", "")
                         .replace("(no hay pytest aquí)", "").replace("con pytest y httpx", "")), "no se corre pytest en el anfitrión"


@pytest.mark.parametrize("nombre", NOMBRES)
def test_sin_arroba_de_archivo_y_con_estructura(nombre):
    texto = leer(nombre)
    assert not re.search(r"(?m)^\s*@\S+\.(md|json|py|feature)", texto), "se usan rutas con Read, no @archivo"
    for titulo in ("Contexto que debes leer", "Entrada", "Salida", "Cómo trabajas"):
        assert f"## {titulo}" in texto, f"a {nombre} le falta la sección «{titulo}»"
    assert "Ejemplo de FORMATO, no de contenido" in texto


def test_el_ejemplo_no_usa_una_historia_real():
    """Los ejemplos usan HU-00; si algún día existe en historias/ o salida/, el ejemplo ya no sería inventado."""
    assert not list((RAIZ / "historias").glob("HU-00*"))
    assert not (RAIZ / "salida" / "HU-00").exists()


def test_el_filtro_distingue_obedecer_de_detectar():
    texto = leer("filtro-seguridad")
    fuera = texto.replace(bloque_seguridad(texto), "")
    assert "Obedecer y detectar son cosas distintas" in fuera
    assert "sospechosa: true" in fuera and "evidencia" in fuera
    assert '"sospechosa": true' in fuera and '"sospechosa": false' in fuera       # el contrato de Veredicto sigue a la vista
