"""Comprobaciones del Paso 2 (sesión 4): solo le pasa JSON de prueba a los hooks y a la verificación.

No abre ni lee ningún archivo del proyecto: la ruta del señuelo viaja como TEXTO dentro del JSON y
rol.py solo la resuelve (no la abre). Uso: .venv/Scripts/python spikes/comprobar_paso2.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable


def hook(datos: dict, defensas_off: bool = False) -> tuple[int, str]:
    entorno = {**os.environ, "DEFENSAS": "0"} if defensas_off else os.environ
    r = subprocess.run([PY, str(RAIZ / "hooks" / "rol.py")], input=json.dumps(datos), text=True,
                       capture_output=True, env=entorno, cwd=RAIZ)
    return r.returncode, r.stderr.strip()


def verificacion(defensas_off: bool) -> str:
    entorno = {**os.environ, "DEFENSAS": "0"} if defensas_off else {**os.environ, "DEFENSAS": "1"}
    r = subprocess.run([PY, "-m", "verificacion", "defensas"], text=True, capture_output=True,
                       env=entorno, cwd=RAIZ)
    return " | ".join(l for l in r.stdout.splitlines() if l.strip())


lectura = {"agent_type": "filtro-seguridad", "tool_name": "Read",
           "tool_input": {"file_path": "secretos_demo.txt"}}
escritura = {"agent_type": "desarrollador", "tool_name": "Write",
             "tool_input": {"file_path": "salida/HU-99/x", "content": "x"}}

print("1) lectura (rol aún no existe en ROLES), DEFENSAS=0 :", hook(lectura, True))
print("2) escritura fuera del rol, DEFENSAS=0 :", hook(escritura, True))
print("3) verificación defensas (activadas) :", verificacion(False))
print("4) verificación defensas (DEFENSAS=0) :", verificacion(True))
