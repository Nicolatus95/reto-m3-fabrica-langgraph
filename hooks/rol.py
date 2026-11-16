"""Hook PreToolUse · Mínima agencia: cada subagente solo lee, escribe y ejecuta lo de su rol.

Claude Code llama a este script antes de CADA herramienta y le pasa por stdin un JSON con
`agent_type` (el nombre del subagente), `tool_name` y `tool_input`.
- Salida 0  → la herramienta se ejecuta.
- Salida 2  → se bloquea, y lo que imprimimos en stderr le llega al agente como motivo.

Es el equivalente de `_dentro_de()` en agentes/base.py de M3: resolver la ruta y rechazar
cualquier cosa fuera de las carpetas permitidas (incluidos los trucos como `historias/../.env`).
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from hooks.roles import ROLES  # noqa: E402

ESCRITURA = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
LECTURA = {"Read", "Glob", "Grep"}
BASES_DE_DATOS = ["salida/*.sqlite", "salida/*.sqlite-wal", "salida/*.sqlite-shm"]    # `*` de fnmatch cruza «/»


def bloquear(motivo: str) -> None:
    print(motivo, file=sys.stderr)
    sys.exit(2)


def relativa(ruta: str) -> str | None:
    """Ruta relativa a la raíz, ya resuelta; None si apunta fuera del proyecto."""
    destino = (RAIZ / ruta).resolve()            # si `ruta` es absoluta, Path ignora RAIZ
    if not destino.is_relative_to(RAIZ):
        return None
    return destino.relative_to(RAIZ).as_posix()


def permitida(ruta: str, patrones: list[str]) -> bool:
    rel = relativa(ruta)
    return rel is not None and any(fnmatch.fnmatch(rel, p) for p in patrones)


# --- curl: solo HTTP(S) hacia la propia app, sin leer ni escribir archivos -----------------------------------------
HOSTS_CURL = {"localhost", "127.0.0.1", "backend", "frontend"}
# Caracteres que bash interpreta ANTES de que curl vea el comando (shlex no los expande, bash sí): sustitución
# (`$`, comilla invertida, `<(`), redirecciones (`>`, `<`), segundo comando en segundo plano (`&`) y saltos de línea.
CARACTERES_SHELL = ("$", "`", "<", ">", "&", "\n", "\r")
OPCIONES_SIN_VALOR = re.compile(r"-[sSfiI]+")             # -s -S -f -i -I, solas o agrupadas (-sf, -sS)
OPCIONES_NUMERICAS = {"-m", "--max-time", "--retry", "--retry-delay"}
NUMERO = re.compile(r"\d+(\.\d+)?")


def revisar_curl(agente: str, tramo: str) -> None:
    """Solo URLs http(s) a localhost/127.0.0.1/backend/frontend y una lista blanca de opciones; si no, exit 2."""
    def no(motivo: str) -> None:
        bloquear(f"Rol {agente}: curl bloqueado: {motivo}. Solo se permiten URLs http(s) a "
                 f"{', '.join(sorted(HOSTS_CURL))} y las opciones -s -S -f -i -I -m/--max-time --retry --retry-delay "
                 f"-w -o /dev/null -X GET|HEAD -H")

    if any(c in tramo for c in CARACTERES_SHELL):
        no("el comando usa $, comilla invertida, <, >, & o saltos de línea (los interpreta la shell)")
    try:
        tokens = shlex.split(tramo)
    except ValueError:
        no("comillas sin cerrar")
    for t in tokens:                                        # también los valores de -H, -w, etc.
        if "@" in t:
            no(f"el argumento «{t}» lleva @ (curl lee archivos con @)")
    urls: list[str] = []
    i = 1                                                   # tokens[0] es «curl»
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("-"):
            if OPCIONES_SIN_VALOR.fullmatch(t):
                i += 1
                continue
            if t not in OPCIONES_NUMERICAS | {"-o", "-X", "-H", "-w"}:
                no(f"la opción {t} no está permitida")
            if i + 1 >= len(tokens):
                no(f"a {t} le falta su valor")
            valor = tokens[i + 1]
            if t in OPCIONES_NUMERICAS and not NUMERO.fullmatch(valor):
                no(f"{t} exige un número, no «{valor}»")
            if t == "-o" and valor != "/dev/null":
                no("-o solo puede escribir en /dev/null")
            if t == "-X" and valor not in ("GET", "HEAD"):
                no("-X solo admite GET o HEAD")
            if t == "-w" and "%output" in valor.lower():
                no("-w con %output{} escribe archivos")
            i += 2
            continue
        urls.append(t)
        i += 1
    if not urls:
        no("falta la URL")
    for url in urls:
        if any(c in url for c in "{}[]\\"):
            no(f"la URL «{url}» lleva {{}}, [] o \\ (globbing de curl)")
        try:
            partes = urlsplit(url)                          # esquema y host ya salen en minúsculas
            puerto = partes.port                            # valida el puerto (ValueError si no es numérico)
        except ValueError:
            no(f"URL no válida: «{url}»")
        if partes.scheme not in ("http", "https") or "://" not in url:
            no(f"la URL «{url}» no es http:// ni https://")
        if partes.hostname not in HOSTS_CURL or puerto == 0:
            no(f"el host de «{url}» no está permitido")


def revisar(agente: str, herramienta: str, entrada: dict) -> None:
    rol = ROLES[agente]
    if os.environ.get("DEFENSAS", "1") == "0" and herramienta not in ESCRITURA:
        return    # sesión 4, solo en clase: sin defensas de lectura ni de terminal, para ver el ataque
    if herramienta in ESCRITURA:
        ruta = entrada.get("file_path") or entrada.get("notebook_path", "")
        if not permitida(ruta, rol.escribe):
            bloquear(f"Rol {agente}: no puedes escribir {ruta}. Permitido: {', '.join(rol.escribe)}")
    elif herramienta in LECTURA:
        ruta = entrada.get("file_path") or entrada.get("path")
        if not ruta:
            bloquear(f"Rol {agente}: indica siempre la carpeta con `path`. Puedes leer: {', '.join(rol.lee)}")
        rel = relativa(ruta)
        if rel is not None and (any(fnmatch.fnmatch(rel, p) for p in BASES_DE_DATOS) or rel.rstrip("/") == "salida"):
            # las bases (memoria.sqlite, fabrica.sqlite, -wal, -shm) no se leen: el agente recibe solo precedentes.md,
            # que el código acota y sanea; y buscar en la raíz de salida/ las alcanzaría
            bloquear(f"Rol {agente}: no puedes leer {ruta}: las bases SQLite de salida/ no se leen "
                     f"(ni se busca en la raíz de salida/: indica salida/HU-xx).")
        if not permitida(ruta, rol.lee + rol.escribe) and not permitida(ruta.rstrip("/") + "/x", rol.lee):
            bloquear(f"Rol {agente}: no puedes leer {ruta}. Permitido: {', '.join(rol.lee)}")
    elif herramienta == "Bash":
        for tramo in re.split(r"&&|\|\||;|\|", entrada.get("command", "")):
            partes = tramo.split()
            # un permiso puede ser varias palabras (".venv/Scripts/python -m pytest"): se compara por prefijo
            texto = " ".join(partes)
            if partes and not any(texto == p or texto.startswith(p + " ") for p in rol.programas):
                permitidos = ", ".join(sorted(rol.programas)) or "ninguno"
                bloquear(f"Rol {agente}: el programa {partes[0]} no está permitido. Permitidos: {permitidos}")
            if partes and partes[0] == "curl":
                revisar_curl(agente, tramo)
            if partes and partes[0] == "cd" and len(partes) > 1 and relativa(partes[1]) is None:
                bloquear(f"Rol {agente}: no puedes salir del proyecto con cd {partes[1]}")
            if texto == "docker compose up" or texto.startswith("docker compose up "):
                # el compose lo escribió un agente: antes del `up` se revisa (falla cerrado si Docker no responde)
                from verificacion.compose_seguro import problemas
                inseguros = problemas()
                if inseguros:
                    bloquear(f"Rol {agente}: el docker-compose.yml no pasa el chequeo de seguridad:\n- " + "\n- ".join(inseguros))


if __name__ == "__main__":
    datos = json.load(sys.stdin)
    agente = datos.get("agent_type")
    if agente in ROLES:                           # el agente principal y otros no se restringen aquí
        revisar(agente, datos["tool_name"], datos.get("tool_input", {}))
    sys.exit(0)