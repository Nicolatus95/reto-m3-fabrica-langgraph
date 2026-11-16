"""Sesión 4 · Corre TODAS las pruebas (API y E2E) contra la app desplegada y resume los fallos.

Deja dos archivos para el triage: salida/HU-xx/resultados.xml (JUnit) y salida/HU-xx/fallos.md (resumen).

Las pruebas son código del agente: corren en el sandbox (verificacion/sandbox.py), con app/tests en solo lectura, una carpeta
de salida temporal para resultados.xml y SIN el entorno del anfitrión (solo URL_API y URL_WEB). La red es una red interna de
Docker (--internal, sin Internet) a la que se conectan los contenedores de la app durante la prueba, con los alias `backend`
y `frontend`. Sin Docker, falla.
"""
import shutil
import xml.etree.ElementTree as ET

from verificacion import sandbox
from verificacion.comun import APP, SALIDA

ENTORNO = {"URL_API": "http://backend:8000", "URL_WEB": "http://frontend"}
COMANDO = ["python", "-m", "pytest", "tests", "-q", "--tb=short", "--junitxml=/out/resultados.xml",
           "-p", "no:cacheprovider", "--output=/tmp/test-results"]


def _escribir_fallos(carpeta, hu: str, log: str) -> None:
    (carpeta / "fallos.md").write_text(f"# Pruebas de {hu}\n\n{log}\n", encoding="utf-8")


def verificar(hu: str | None = None) -> tuple[bool, str]:
    if not hu:
        return False, "Indica la historia: python -m verificacion e2e HU-01"
    carpeta = SALIDA / hu
    carpeta.mkdir(parents=True, exist_ok=True)
    reporte = carpeta / "resultados.xml"
    reporte.unlink(missing_ok=True)                # un resultado viejo nunca se confunde con el de esta corrida
    disponible, mensaje = sandbox.docker_disponible()
    if not disponible:
        _escribir_fallos(carpeta, hu, mensaje)
        return False, mensaje
    conectados, error = sandbox.conectar_app_a_red_e2e()
    if error:
        sandbox.desconectar_app_de_red_e2e(conectados)
        _escribir_fallos(carpeta, hu, error)
        return False, error
    salida = sandbox.carpeta_de_salida()
    try:
        r = sandbox.ejecutar(sandbox.IMAGEN, COMANDO, montajes=[sandbox.Montaje(APP / "tests", "/work/tests"),
                                                                 sandbox.Montaje(salida, "/out", escritura=True)],
                             red=sandbox.RED_E2E, limites=sandbox.LIMITES_E2E, entorno=ENTORNO, timeout=900)
        if (salida / "resultados.xml").exists():
            shutil.copyfile(salida / "resultados.xml", reporte)
    finally:
        sandbox.desconectar_app_de_red_e2e(conectados)
        shutil.rmtree(salida, ignore_errors=True)
    fallos = []
    if reporte.exists():
        for caso in ET.parse(reporte).getroot().iter("testcase"):
            for problema in list(caso.findall("failure")) + list(caso.findall("error")):
                fallos.append(f"- {caso.get('classname')}::{caso.get('name')}\n"
                              f"  {(problema.get('message') or '')[:400]}")
    resumen = r.salida.strip().splitlines()[-1] if r.salida.strip() else "sin salida"
    log = f"{resumen}\n" + "\n".join(fallos)
    _escribir_fallos(carpeta, hu, log)
    return r.ok, log
