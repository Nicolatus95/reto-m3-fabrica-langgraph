"""Corre DENTRO del sandbox (sin red): ¿el backend que escribió el desarrollador arranca y responde /api/salud?

Monta app/backend en /src (solo lectura). Copia el backend a /tmp (escribible), comprueba que sus dependencias estén en
la imagen, arranca uvicorn en 127.0.0.1:8010 y sondea /api/salud. Código de salida 0 = pasó. Archivo nuestro: ningún
agente lo escribe.
"""
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from importlib import metadata
from pathlib import Path

ORIGEN = Path("/src")
COPIA = Path("/tmp/backend")
PUERTO = 8010
INTENTOS = 20


def dependencias_que_faltan() -> list[str]:
    """Nombres de requirements.txt que no están instalados en la imagen (versiones fijadas en sandbox/Dockerfile)."""
    archivo = ORIGEN / "requirements.txt"
    if not archivo.exists():
        return []
    faltan = []
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#")[0].strip()
        if not linea or linea.startswith("-"):
            continue
        nombre = re.split(r"[\[<>=!~;@ ]", linea, maxsplit=1)[0]
        try:
            metadata.version(nombre)
        except metadata.PackageNotFoundError:
            faltan.append(nombre)
    return faltan


def main() -> int:
    if not (ORIGEN / "main.py").exists():
        print("No existe app/backend/main.py")
        return 1
    faltan = dependencias_que_faltan()
    if faltan:
        print("Dependencias que no están en el sandbox: " + ", ".join(faltan) + ".\n"
              "El backend solo puede usar las de sandbox/Dockerfile (fastapi, uvicorn, sqlalchemy, pydantic, httpx, pytest).")
        return 1
    shutil.copytree(ORIGEN, COPIA, ignore=shutil.ignore_patterns("datos", "__pycache__", "node_modules", ".venv"))
    proceso = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PUERTO)],
                               cwd=COPIA, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = f"http://127.0.0.1:{PUERTO}/api/salud"
    try:
        for _ in range(INTENTOS):
            if proceso.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status < 400:
                        print(f"{url} -> {r.status}")
                        return 0
            except OSError:
                pass
            time.sleep(1)
    finally:
        proceso.terminate()
        try:
            salida = proceso.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            proceso.kill()
            salida = proceso.communicate()[0]
    print(f"{url} no respondió en {INTENTOS} s\n{salida[-3000:]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
