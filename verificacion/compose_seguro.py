"""Chequeo determinista de app/docker-compose.yml ANTES de `docker compose up`.

El agente de despliegue escribe ese archivo, y `up` lo ejecuta con Docker: un compose hostil podría montar la raíz del
anfitrión o el socket de Docker, correr `privileged` o compartir la red y los procesos del anfitrión. Aquí se normaliza con
`docker compose config --format json` (rutas ya absolutas, sin atajos) y se rechaza lo peligroso.

Rechaza: redes external o con nombre explícito (name:), privileged, network_mode/pid/ipc/uts/userns_mode/cgroup compartidos con el anfitrión u otro contenedor, cap_add,
devices, security_opt, montajes (bind) fuera de app/, el socket o la tubería de Docker, contextos de build fuera de app/,
volúmenes con driver_opts, configs/secrets con archivos, y en el texto: interpolación de variables ($), env_file, include
y extends (leerían archivos o variables del anfitrión que `config` ya no distingue).
Lo usan verificacion/despliegue.py (redesplegar) y hooks/rol.py (cuando el agente corre `docker compose up`).
"""
import json
import re
from pathlib import Path

from verificacion.comun import APP
from verificacion.sandbox import lanzar

COMPARTIDOS = ("pid", "ipc", "uts", "userns_mode", "cgroup")      # «host», «container:x» o «service:x» comparten con el anfitrión
SOCKETS = ("docker.sock", "docker_engine", "/pipe/", "\\pipe\\")
TEXTO_PROHIBIDO = [(re.compile(r"\$"), "usa interpolación de variables ($): leería el entorno del anfitrión"),
                   (re.compile(r"^\s*env_file\s*:", re.MULTILINE), "usa env_file"),
                   (re.compile(r"^\s*include\s*:", re.MULTILINE), "usa include"),
                   (re.compile(r"^\s*extends\s*:", re.MULTILINE), "usa extends")]


def _dentro(ruta: str, app: Path) -> bool:
    try:
        return Path(ruta).resolve().is_relative_to(app.resolve())
    except (OSError, ValueError):
        return False


def _compartido(valor) -> bool:
    texto = str(valor or "").lower()
    return texto == "host" or texto.startswith(("container:", "service:"))


def evaluar(config: dict, texto: str, app: Path = APP) -> list[str]:
    """Problemas de un compose ya normalizado (`config`) y su texto original. Lista vacía = seguro."""
    problemas = [f"el compose {motivo}" for patron, motivo in TEXTO_PROHIBIDO if patron.search(texto)]
    for nombre, servicio in (config.get("services") or {}).items():
        def mal(motivo: str, nombre=nombre) -> None:
            problemas.append(f"servicio «{nombre}»: {motivo}")
        if servicio.get("privileged"):
            mal("privileged")
        modo_red = servicio.get("network_mode")
        if modo_red and modo_red not in ("none", "bridge"):
            mal(f"network_mode: {modo_red}")
        for campo in COMPARTIDOS:
            if _compartido(servicio.get(campo)):
                mal(f"{campo}: {servicio[campo]} (comparte con el anfitrión u otro contenedor)")
        for campo in ("cap_add", "devices", "security_opt"):
            if servicio.get(campo):
                mal(f"{campo} no está permitido")
        for volumen in servicio.get("volumes") or []:
            if not isinstance(volumen, dict):
                mal(f"montaje con formato no reconocido: {volumen}")
                continue
            origen, destino = str(volumen.get("source") or ""), str(volumen.get("target") or "")
            if any(s in (origen + destino).lower() for s in SOCKETS) or volumen.get("type") == "npipe":
                mal(f"monta el socket de Docker: {origen or destino}")
            elif volumen.get("type") == "bind" and not _dentro(origen, app):
                mal(f"monta {origen}, que está fuera de app/")
        build = servicio.get("build")
        contextos = [build.get("context")] if isinstance(build, dict) else [build] if build else []
        if isinstance(build, dict):
            contextos += [v for v in (build.get("additional_contexts") or {}).values() if "://" not in str(v)]
        for contexto in contextos:
            if contexto and not _dentro(str(contexto), app):
                mal(f"el contexto de build {contexto} está fuera de app/")
    proyecto = config.get("name") or app.resolve().name
    for clave, red in (config.get("networks") or {}).items():
        red = red or {}
        if red.get("external"):
            problemas.append(f"red «{clave}»: external no está permitido (usaría una red que ya existe, como fabrica_sandbox)")
        elif red.get("name") not in (None, f"{proyecto}_{clave}"):
            problemas.append(f"red «{clave}»: nombre explícito {red.get('name')!r} no permitido (podría ocupar una red del "
                             f"sandbox como fabrica_sandbox); la red debe llamarse {proyecto}_{clave}")
    for nombre, volumen in (config.get("volumes") or {}).items():
        if (volumen or {}).get("driver_opts"):
            problemas.append(f"volumen «{nombre}»: driver_opts no está permitido (podría montar rutas del anfitrión)")
    for seccion in ("configs", "secrets"):
        if config.get(seccion):
            problemas.append(f"el compose define {seccion}: no está permitido (referencian archivos del anfitrión)")
    return problemas


def problemas(app: Path = APP) -> list[str]:
    """Normaliza app/docker-compose.yml con `docker compose config` y lo evalúa. Falla cerrado ante cualquier duda."""
    archivo = app / "docker-compose.yml"
    if not archivo.exists():
        return ["No existe app/docker-compose.yml"]
    try:
        r = lanzar(["docker", "compose", "-f", str(archivo), "--project-directory", str(app), "config", "--format", "json"], 60)
        config = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, ValueError) as e:
        return [f"No se pudo normalizar el compose ({type(e).__name__}): no se despliega"]
    except Exception as e:                      # subprocess.TimeoutExpired u otro fallo del CLI
        return [f"No se pudo normalizar el compose ({type(e).__name__}): no se despliega"]
    if config is None:
        return [f"docker compose config falló: {(r.stderr or r.stdout).strip()[-400:]}"]
    return evaluar(config, archivo.read_text(encoding="utf-8"), app)
