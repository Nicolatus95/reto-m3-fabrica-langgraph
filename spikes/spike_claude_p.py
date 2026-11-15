"""Spike del reto · Llamar a `claude -p` desde Python (sin API key) y leer su resultado como datos.

Solo vive en spikes/: no toca agentes, skills, hooks ni verificacion/.
Uso: .venv/Scripts/python spikes/spike_claude_p.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parent.parent
CAMPOS = ("result", "structured_output", "total_cost_usd", "duration_ms", "is_error")


def ejecutar(prompt: str, *, modelo: str | None = None, esquema: dict | type[BaseModel] | None = None,
             herramientas: str | None = None, entorno_extra: dict[str, str] | None = None,
             timeout: int = 600) -> dict:
    """Corre `claude -p` y devuelve result, structured_output, total_cost_usd, duration_ms e is_error.

    - modelo: alias o id de modelo (--model); None usa el de la sesión.
    - esquema: JSON Schema (dict) o modelo Pydantic para la salida estructurada (--json-schema).
    - herramientas: lista separada por comas para --tools; "" = sin herramientas; None = las de siempre.
    - entorno_extra: variables que se agregan al entorno del proceso hijo (por ejemplo DEFENSAS).
    """
    ejecutable = shutil.which("claude")
    if ejecutable is None:
        raise RuntimeError("No se encontró `claude` en el PATH")
    comando = [ejecutable, "-p", "--output-format", "json", "--permission-mode", "acceptEdits"]
    if modelo:
        comando += ["--model", modelo]
    if esquema is not None:
        schema = esquema.model_json_schema() if isinstance(esquema, type) else esquema
        comando += ["--json-schema", json.dumps(schema)]
    if herramientas is not None:
        comando += ["--tools", herramientas]
    comando += ["--", prompt]                      # «--» corta las opciones variádicas (--tools) antes del prompt

    entorno = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # solo la sesión de claude auth login
    entorno.update(entorno_extra or {})

    r = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=entorno, timeout=timeout)
    try:
        datos = json.loads(r.stdout)
    except json.JSONDecodeError:                     # no salió JSON: el proceso falló antes de responder
        return {"result": (r.stdout + r.stderr).strip()[-1500:], "structured_output": None,
                "total_cost_usd": None, "duration_ms": None, "is_error": True, "codigo_salida": r.returncode}
    return {**{campo: datos.get(campo) for campo in CAMPOS}, "codigo_salida": r.returncode}


def resumen(titulo: str, r: dict) -> None:
    texto = (r["result"] or "").strip().replace("\n", " ")
    print(f"\n=== {titulo}")
    print(f"is_error={r['is_error']} · código de salida={r['codigo_salida']} · costo=${r['total_cost_usd']} · "
          f"{r['duration_ms']} ms")
    print(f"result: {texto[:300]}")
    print(f"structured_output: {r['structured_output']}")


# --- (a) Un skill desde Python; el CÓDIGO lee el veredicto, no el modelo --------------------------
def demo_skill() -> dict | None:
    ruta = RAIZ / "salida" / "HU-01" / "veredicto.json"
    antes = ruta.stat().st_mtime if ruta.exists() else None
    r = ejecutar("/filtrar historias/HU-01-registrar-empleado.md")
    resumen("a) /filtrar HU-01 desde Python", r)
    if not ruta.exists():
        print("FALLA: no existe salida/HU-01/veredicto.json")
        return r
    sospechosa = json.loads(ruta.read_text(encoding="utf-8"))["sospechosa"]
    print(f"veredicto.json reescrito por el agente: {ruta.stat().st_mtime != antes}")
    print(f"sospechosa (leída por el código): {sospechosa!r}  · esperado False → "
          f"{'OK' if sospechosa is False else 'FALLA'}")
    return r


# --- (b) Salida estructurada sin herramientas (para el futuro revisor) ----------------------------
class Revision(BaseModel):
    aprobado: bool
    observaciones: list[str]


FRAGMENTO = '''def leer_config(ruta):
    try:
        f = open(ruta)
        return json.load(f)
    except:
        pass
'''


def demo_estructurada() -> dict:
    prompt = ("Eres revisor de código. Revisa este fragmento de Python y responde solo con el contrato pedido: "
              "aprobado=false si hay algún problema; en observaciones, una frase por problema.\n\n" + FRAGMENTO)
    r = ejecutar(prompt, modelo="haiku", esquema=Revision, herramientas="")
    resumen("b) revisión estructurada (haiku, sin herramientas)", r)
    try:
        revision = Revision.model_validate(r["structured_output"])
    except Exception as e:                           # structured_output vacío o fuera de contrato
        print(f"FALLA: la salida no cumple el contrato Revision: {e}")
        return r
    ok = revision.aprobado is False and any("except" in o.lower() for o in revision.observaciones)
    print(f"aprobado={revision.aprobado} · observaciones={revision.observaciones}")
    print(f"esperado: aprobado False y mención del except → {'OK' if ok else 'FALLA'}")
    return r


# --- (c) El entorno llega a los hooks -------------------------------------------------------------
def demo_entorno() -> list[dict]:
    prompt = "Ejecuta .venv/Scripts/python -m verificacion defensas y responde solo con lo que imprimió"
    resultados = []
    for etiqueta, extra, esperado in (("DEFENSAS=0", {"DEFENSAS": "0"}, "DEFENSAS DESACTIVADAS"),
                                      ("sin entorno_extra", None, "DEFENSAS ACTIVADAS")):
        r = ejecutar(prompt, entorno_extra=extra)
        resumen(f"c) entorno: {etiqueta}", r)
        print(f"esperado «{esperado}» → {'OK' if esperado in (r['result'] or '') else 'FALLA'}")
        resultados.append(r)
    return resultados


# --- (d) Manejo de error: ¿cómo se detecta en el grafo? --------------------------------------------
def demo_error() -> dict:
    r = ejecutar("/skill-que-no-existe")
    resumen("d) skill que no existe", r)
    print(f"→ para el grafo: is_error={r['is_error']!r}, código de salida={r['codigo_salida']!r}, "
          f"result vacío={not (r['result'] or '').strip()}")
    return r


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    todas = [demo_skill(), demo_estructurada(), *demo_entorno(), demo_error()]
    costo = sum((r or {}).get("total_cost_usd") or 0 for r in todas)
    print(f"\n=== Costo total del spike (a + b + c + d): ${costo:.4f}")
