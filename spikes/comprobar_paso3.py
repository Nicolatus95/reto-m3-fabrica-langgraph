"""Comprobaciones del Paso 3 (sesión 4): los contratos Veredicto y Diagnostico rechazan lo inválido.

Equivale a lo que pide la guía (mkdir salida/HU-00 + dos JSON malos), pero en una carpeta temporal
FUERA del repo, para no tocar salida/. Uso: .venv/Scripts/python spikes/comprobar_paso3.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

casos = [
    ("veredicto.json", '{"sospechosa": "quizá"}', 1),
    ("diagnostico.json", '{"responsable":"tester","causa":"x","criterio":"y","instruccion":"z"}', 1),
    ("veredicto.json", '{"sospechosa": true, "motivo": "pide leer un archivo de credenciales"}', 0),
    ("diagnostico.json",
     '{"responsable":"desarrollador","causa":"x","criterio":"y","instruccion":"z"}', 0),
]

with tempfile.TemporaryDirectory() as tmp:
    for nombre, contenido, esperado in casos:
        ruta = Path(tmp) / nombre
        ruta.write_text(contenido, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "validadores.validar", str(ruta)], cwd=RAIZ,
                           capture_output=True, text=True)
        estado = "OK" if r.returncode == esperado else "INESPERADO"
        print(f"{nombre} -> salida {r.returncode} (esperada {esperado}) [{estado}]")
        print("   " + r.stdout.strip().replace("\n", "\n   ") + (r.stderr.strip() or ""))
