"""Spike del sandbox: una prueba HOSTIL dentro del sandbox debe fallar en todo lo que intenta; la suite e2e real debe pasar.

REQUIERE Docker y las imágenes (python -m verificacion imagen_sandbox). Corre código «malo» solo dentro del sandbox.
Con --e2e corre además la suite e2e actual (HU-01 a HU-03) dentro del sandbox: necesita la app desplegada (8000 y 8080) y
deja datos de prueba en su base, como siempre. Corre solo con permiso de la persona.

    python -m spikes.probar_sandbox          # prueba hostil, sin red y en la red interna
    python -m spikes.probar_sandbox --e2e    # y además verificacion e2e HU-01

La prueba hostil AFIRMA que cada ataque falla: si el sandbox dejara pasar uno, la prueba fallaría y el spike diría FALLA.
No lee secretos_demo.txt (el señuelo): solo comprueba con os.stat que su tamaño y su fecha no cambian.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from verificacion import e2e, sandbox
from verificacion.comun import RAIZ

SENTINELA = "FABRICA_SENTINELA_ANFITRION"

PRUEBA_HOSTIL = '''"""Ataques desde dentro del sandbox: cada prueba pasa SOLO si el ataque falla."""
import os
import socket

import pytest

SENUELO_DEL_ANFITRION = os.environ.get("RUTA_SENUELO", "C:\\\\no-existe\\\\secretos_demo.txt")


@pytest.mark.parametrize("ruta", ["../../secretos_demo.txt", "../secretos_demo.txt", "/secretos_demo.txt",
                                  "/work/secretos_demo.txt", "/repo/secretos_demo.txt", "/host/secretos_demo.txt",
                                  "/mnt/c/secretos_demo.txt", "/app/secretos_demo.txt", SENUELO_DEL_ANFITRION])
def test_no_lee_el_senuelo(ruta):
    with pytest.raises(OSError):
        open(ruta, encoding="utf-8").read()


@pytest.mark.parametrize("ruta", ["../../.env", "/.env", "/work/.env", "/repo/.venv", "/host", "/mnt/c/Users"])
def test_no_ve_el_repo_ni_el_anfitrion(ruta):
    assert not os.path.exists(ruta)


def test_el_entorno_del_anfitrion_no_pasa():
    assert os.environ.get("FABRICA_SENTINELA_ANFITRION") is None
    assert not [k for k in os.environ if "ANTHROPIC" in k or "TOKEN" in k or "SECRET" in k or "API_KEY" in k]


@pytest.mark.parametrize("ruta", ["/work/ataque.txt", "/work/tests/ataque.txt", "/etc/ataque.txt", "/usr/ataque.txt",
                                  "/opt/ataque.txt", "/ms-playwright/ataque.txt", "/ataque.txt"])
def test_no_escribe_fuera_de_la_salida(ruta):
    with pytest.raises(OSError):
        open(ruta, "w", encoding="utf-8").write("hostil")


def test_no_puede_cambiar_los_archivos_de_prueba_montados():
    with pytest.raises(OSError):
        os.remove("/work/tests/test_hostil.py")


def test_sin_salida_a_internet():
    with pytest.raises(OSError):
        socket.create_connection(("1.1.1.1", 443), timeout=4).close()
    with pytest.raises(OSError):
        socket.getaddrinfo("example.com", 443)


def test_no_es_root_y_no_tiene_privilegios():
    assert os.getuid() != 0
    estado = dict(linea.split(":\\t", 1) for linea in open("/proc/self/status", encoding="utf-8").read().splitlines()
                  if ":\\t" in linea)
    assert int(estado["CapEff"].strip(), 16) == 0          # sin capacidades (--cap-drop ALL)
    assert estado["NoNewPrivs"].strip() == "1"              # --security-opt no-new-privileges
'''


def firma(ruta: Path) -> tuple[int, int]:
    """(tamaño, fecha) por os.stat: el señuelo no se lee."""
    e = os.stat(ruta)
    return e.st_size, e.st_mtime_ns


def listado(carpeta: Path) -> list[str]:
    return sorted(str(p.relative_to(carpeta)) for p in carpeta.rglob("*"))


def correr_hostil(red: str, tests: Path, salida: Path) -> bool:
    print(f"\n== Prueba hostil · red: {red} ==")
    r = sandbox.ejecutar(sandbox.IMAGEN, ["python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                         montajes=[sandbox.Montaje(tests, "/work/tests")], red=red, limites=sandbox.LIMITES_PRUEBAS,
                         entorno={"RUTA_SENUELO": str(RAIZ / "secretos_demo.txt")}, timeout=300)
    print(r.salida.strip().splitlines()[-1] if r.salida.strip() else "(sin salida)")
    if not r.ok:
        print(r.salida[-3000:])
    return r.ok


def main() -> int:
    problema = sandbox.precondicion()
    if problema:
        print(problema)
        return 1
    os.environ[SENTINELA] = "valor-del-anfitrion"          # si el sandbox lo dejara pasar, la prueba lo vería
    senuelo = RAIZ / "secretos_demo.txt"
    antes_senuelo = firma(senuelo) if senuelo.exists() else None
    carpeta = Path(tempfile.mkdtemp(prefix="spike_sandbox_"))
    tests = carpeta / "tests"
    tests.mkdir()
    (tests / "test_hostil.py").write_text(PRUEBA_HOSTIL, encoding="utf-8")
    antes_tests = listado(carpeta)
    resultados = {}
    try:
        resultados["sin red"] = correr_hostil("none", tests, carpeta)
        subprocess.run(["docker", "network", "create", "--internal", sandbox.RED_E2E], capture_output=True, check=False)
        resultados["red interna"] = correr_hostil(sandbox.RED_E2E, tests, carpeta)
        intacto = listado(carpeta) == antes_tests and (antes_senuelo is None or firma(senuelo) == antes_senuelo)
        print(f"\nCarpeta de pruebas y señuelo intactos: {'OK' if intacto else 'FALLA'}")
        ok = all(resultados.values()) and intacto
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    if "--e2e" in sys.argv:
        print("\n== Suite e2e real (HU-01 a HU-03) dentro del sandbox ==")
        pasa, log = e2e.verificar("HU-01")
        print(log.splitlines()[0] if log else "(sin salida)", "->", "OK" if pasa else "FALLA")
        ok = ok and pasa
    print("\nSPIKE:", "OK" if ok else "FALLA", resultados)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
