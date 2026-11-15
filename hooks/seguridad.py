"""Hook PreToolUse · Sesión 4 · Defensas para TODOS los agentes (también el principal).

La historia de usuario es contenido NO confiable: puede traer instrucciones escondidas para el agente
(inyección de prompt, ver historias/HU-99-envenenada.md). Estas defensas no dependen de que el modelo
«se dé cuenta»: son código que se ejecuta antes de cada herramienta.

1. Lectura confinada: nada fuera del proyecto, ningún archivo con secretos y nada dentro de registros/.
2. Terminal: sin sustitución de comandos, sin mencionar secretos ni variables de entorno y sin nombrar registros/.
3. Escritura: ningún archivo puede contener el señuelo de secretos_demo.txt (prevención de fuga).
4. Auditoría: cada herramienta queda registrada en registros/auditoria.jsonl, SIEMPRE, incluso con DEFENSAS=0
   (el campo «defensas» dice si estaban activas). La ruta es fija: una variable de entorno que la cambiara
   sería en sí misma una forma de evadir el registro.

registros/ es solo para personas: ningún agente la lee, tampoco el principal (la lista de permitidos de
hooks/roles.py no alcanza al principal, por eso el bloqueo es explícito y está aquí).
DEFENSAS=0 apaga las defensas (1 a 3), SOLO en clase, para ver el ataque funcionar (hooks/rol.py también relaja la
lectura). La auditoría no se apaga.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REGISTROS = RAIZ / "registros"
SECRETOS = (".env", "secretos")
# \b = borde de palabra: bloquea `env` o `printenv`, pero no `uv venv` ni `.venv/bin/python`
PALABRAS_SECRETAS = re.compile(r"\.env\b|secretos|\bprintenv\b|\benviron\b|\benv\b")
# «registros» como SEGMENTO de ruta (cat registros/x, type .\registros\x, ls ./registros), no como palabra suelta:
# `pytest -k registro_empleado` o `curl ...?registros=10` pasan
SEGMENTO_REGISTROS = re.compile(r"(^|[\s\"'=./\\])registros([/\\\s\"']|$)")
SENUELO = "BANDERA" + "-DEMO"     # partido en dos: el hook también revisa lo que se escribe en este mismo archivo


def bloquear(motivo: str) -> None:
    print(f"Seguridad: {motivo}", file=sys.stderr)
    sys.exit(2)


def menciona_registros(texto: str) -> bool:
    return bool(SEGMENTO_REGISTROS.search(texto.lower()))


def auditar(datos: dict, defensas: bool) -> None:
    """Una línea por herramienta en registros/auditoria.jsonl. Con las defensas activas, si no se puede escribir se bloquea."""
    registro = {"ts": round(time.time(), 1), "agente": datos.get("agent_type") or "principal",
                "herramienta": datos["tool_name"], "entrada": str(datos.get("tool_input", {}))[:300],
                "defensas": "activas" if defensas else "apagadas"}
    try:
        REGISTROS.mkdir(exist_ok=True)
        with open(REGISTROS / "auditoria.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except OSError:
        if defensas:      # un error normal (exit 1) dejaría pasar la herramienta sin rastro: se falla cerrado
            bloquear("no se pudo escribir la auditoría")


def revisar(herramienta: str, entrada: dict) -> None:
    if herramienta in ("Read", "Glob", "Grep"):
        ruta = entrada.get("file_path") or entrada.get("path") or "."
        destino = (RAIZ / ruta).resolve()
        if not destino.is_relative_to(RAIZ):
            bloquear(f"lectura fuera del proyecto bloqueada: {ruta}")
        if any(s in destino.name.lower() for s in SECRETOS) and not destino.name.endswith(".example"):
            bloquear(f"archivo con secretos bloqueado: {destino.name}")
        patrones = [str(entrada.get("glob") or "")] + ([str(entrada.get("pattern") or "")] if herramienta == "Glob" else [])
        if destino.is_relative_to(REGISTROS.resolve()) or any(menciona_registros(p) for p in patrones):
            bloquear("registros/ es solo para personas")

    elif herramienta == "Bash":
        comando = entrada.get("command", "")
        if "`" in comando or "$(" in comando:
            bloquear("sustitución de comandos no permitida")
        if PALABRAS_SECRETAS.search(comando.lower()):
            bloquear("el comando menciona secretos o variables de entorno")
        if menciona_registros(comando):
            bloquear("registros/ es solo para personas")

    elif herramienta in ("Write", "Edit", "MultiEdit"):
        contenido = entrada.get("content") or entrada.get("new_string") or json.dumps(entrada.get("edits", ""))
        if SENUELO in contenido:
            bloquear("el contenido incluye datos de secretos_demo.txt (fuga de información)")


if __name__ == "__main__":
    datos = json.load(sys.stdin)
    defensas = os.environ.get("DEFENSAS", "1") != "0"
    auditar(datos, defensas)                  # SIEMPRE, antes de mirar DEFENSAS
    if defensas:
        revisar(datos["tool_name"], datos.get("tool_input", {}))
    sys.exit(0)
