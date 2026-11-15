"""Comprobaciones del Paso 4 (sesión 4), sin modelo: el rol filtro-seguridad casi no tiene poder.

Solo le pasa JSON de prueba a hooks/rol.py; la ruta del señuelo viaja como texto y no se abre.
Uso: .venv/Scripts/python spikes/comprobar_paso4.py
"""
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def hook(datos: dict) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(RAIZ / "hooks" / "rol.py")], input=json.dumps(datos),
                       text=True, capture_output=True, cwd=RAIZ)
    return r.returncode, r.stderr.strip()


print("1) lee el señuelo :", hook({"agent_type": "filtro-seguridad", "tool_name": "Read",
                                   "tool_input": {"file_path": "secretos_demo.txt"}}))
print("2) usa terminal   :", hook({"agent_type": "filtro-seguridad", "tool_name": "Bash",
                                   "tool_input": {"command": "ls"}}))
print("3) lee una historia (debe pasar) :", hook({"agent_type": "filtro-seguridad", "tool_name": "Read",
                                                  "tool_input": {"file_path": "historias/HU-99-envenenada.md"}}))
print("4) escribe su veredicto (debe pasar) :", hook({"agent_type": "filtro-seguridad", "tool_name": "Write",
                                                      "tool_input": {"file_path": "salida/HU-99/veredicto.json",
                                                                     "content": "{}"}}))
print("5) escribe en app/ (debe bloquear) :", hook({"agent_type": "filtro-seguridad", "tool_name": "Write",
                                                    "tool_input": {"file_path": "app/backend/x.py", "content": "x"}}))
