"""Llamar a `claude -p` desde Python (sin API key) y leer su resultado como datos.

Promovida del spike spikes/spike_claude_p.py. Esta capa NO decide si un paso salió bien: `is_error=False`
solo significa que el proceso respondió (un skill inexistente también devuelve `is_error=False`). Quien
juzga es el grafo, mirando el artefacto que el skill debía dejar.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parent.parent
MAX_PROMPT_ARGUMENTO = 20_000     # caracteres; por encima el prompt se envía por stdin
CAMPOS = ("result", "structured_output", "total_cost_usd", "duration_ms", "is_error")


def ejecutar(prompt: str, *, modelo: str, esquema: dict | type[BaseModel] | None = None,
             herramientas: str | None = None, entorno_extra: dict[str, str] | None = None,
             timeout: int = 1800) -> dict:
    """Corre `claude -p` y devuelve result, structured_output, total_cost_usd, duration_ms, is_error y codigo_salida.

    - modelo: obligatorio; cada llamada fija su modelo (alias o id) para que el costo sea predecible.
    - esquema: JSON Schema (dict) o modelo Pydantic para la salida estructurada (--json-schema).
    - herramientas: lista separada por comas para --tools; "" = sin herramientas; None = las de siempre.
    - entorno_extra: variables que se agregan al entorno del proceso hijo (por ejemplo DEFENSAS).
    - Un fallo de infraestructura (sin `claude`, sin JSON, tiempo agotado) se devuelve con is_error=True e infra=True.
    """
    ejecutable = shutil.which("claude")
    if ejecutable is None:
        return _fallo("No se encontró `claude` en el PATH", None)
    comando = [ejecutable, "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
               "--model", modelo]
    if esquema is not None:
        schema = esquema.model_json_schema() if isinstance(esquema, type) else esquema
        comando += ["--json-schema", json.dumps(schema)]
    if herramientas is not None:
        comando += ["--tools", herramientas]
    por_stdin = len(prompt) > MAX_PROMPT_ARGUMENTO  # Windows limita la línea de comandos a ~32 KB: lo largo va por stdin
    if not por_stdin:
        comando += ["--", prompt]                  # «--» corta las opciones variádicas (--tools) antes del prompt

    entorno = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # solo la sesión de `claude auth login`
    entorno.update(entorno_extra or {})
    try:
        r = subprocess.run(comando, check=False, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=entorno, timeout=timeout, input=prompt if por_stdin else None)
    except subprocess.TimeoutExpired:
        return _fallo(f"`claude -p` superó {timeout} s", -1)
    try:
        datos = json.loads(r.stdout)
    except json.JSONDecodeError:                     # no salió JSON: el proceso falló antes de responder
        return _fallo((r.stdout + r.stderr).strip()[-1500:], r.returncode)
    return {**{campo: datos.get(campo) for campo in CAMPOS}, "codigo_salida": r.returncode, "infra": False}


def _fallo(mensaje: str, codigo: int | None) -> dict:
    """Respuesta uniforme cuando no hubo JSON que leer."""
    return {"result": mensaje, "structured_output": None, "total_cost_usd": None, "duration_ms": None,
            "is_error": True, "codigo_salida": codigo, "infra": True}


class ErrorInfraestructura(Exception):
    """`claude -p` no respondió (sin `claude`, sin JSON o tiempo agotado): un fallo de infraestructura, no de contenido.

    Es lo único que el grafo reintenta (RetryPolicy). Un artefacto inválido o un `is_error` que viene dentro de un
    JSON válido NO son infraestructura: siguen el camino de siempre (escalar).
    """


def ejecutar_exigiendo(prompt: str, **kwargs) -> dict:
    """Como `ejecutar`, pero un fallo de infraestructura lanza ErrorInfraestructura (con el motivo, nunca el texto crudo)."""
    respuesta = ejecutar(prompt, **kwargs)
    if respuesta.get("infra"):
        raise ErrorInfraestructura(f"claude -p sin respuesta (código de salida {respuesta.get('codigo_salida')})")
    return respuesta
