"""Ejecutor común del sandbox: el código que escribe un agente NUNCA corre en el anfitrión, corre aquí.

Cada ejecución es un `docker run --rm` endurecido: raíz de solo lectura con tmpfs, sin capacidades, sin privilegios nuevos,
usuario no root, con límites de memoria, CPU y procesos, con timeout, SIN variables de entorno del anfitrión (solo las que se
pasan, una por una) y con montajes mínimos: la carpeta que se ejecuta en solo lectura más una carpeta de salida temporal
(fuera del repo). Nunca la raíz del repo, .venv, registros/, hooks/, .claude/ ni secretos_demo.txt.

Si Docker no está disponible, la verificación FALLA (falla cerrado): no existe una ruta de respaldo que corra en el anfitrión.
"""
import os
import re
import secrets
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from verificacion.comun import APP, RAIZ

IMAGEN = "fabrica-sandbox:1"             # pytest, pytest-playwright, httpx y las dependencias del backend (sandbox/Dockerfile)
IMAGEN_NODE = "fabrica-sandbox-node:1"   # node para el front-end (sandbox/Dockerfile.node)
RED_E2E = "fabrica_sandbox"              # red interna de Docker (--internal): sin salida a Internet
COMANDO_CONSTRUIR = "python -m verificacion imagen_sandbox"

# Nada de esto se monta jamás (ni nada que lo contenga: montar un padre expondría su contenido)
PROHIBIDOS = [RAIZ / ".venv", RAIZ / "registros", RAIZ / "secretos_demo.txt", RAIZ / ".env", RAIZ / ".git",
              RAIZ / "hooks", RAIZ / ".claude"]


@dataclass(frozen=True)
class Limites:
    memoria: str = "512m"
    cpus: float = 1.0
    pids: int = 128
    tmp: str = "64m"                 # tamaño del tmpfs de /tmp (cuenta para la memoria)
    shm: str | None = None           # /dev/shm (Chromium necesita más)


LIMITES_PRUEBAS = Limites(memoria="512m", cpus=1.0, pids=128, tmp="64m")
LIMITES_BACKEND = Limites(memoria="512m", cpus=1.0, pids=128, tmp="128m")
LIMITES_E2E = Limites(memoria="2g", cpus=2.0, pids=512, tmp="256m", shm="1g")
LIMITES_NODE = Limites(memoria="1536m", cpus=2.0, pids=256, tmp="768m")


@dataclass(frozen=True)
class Montaje:
    origen: Path
    destino: str
    escritura: bool = False


@dataclass(frozen=True)
class Volumen:
    """Volumen de Docker temporal (nombre, destino): para pasar node_modules de la fase 1 a la fase 2 del front-end."""
    nombre: str
    destino: str
    escritura: bool = True


@dataclass
class Resultado:
    ok: bool
    salida: str
    codigo: int | None = None


def lanzar(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Corre un comando de Docker en el anfitrión (el CLI, no código del agente). Los tests lo sustituyen por un doble."""
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=False)


# --- Disponibilidad -------------------------------------------------------------------------------------------
def docker_disponible() -> tuple[bool, str]:
    """¿Hay un motor de Docker? Si no, nada corre: falla cerrado."""
    try:
        r = lanzar(["docker", "info", "--format", "{{.ServerVersion}}"], 30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"Docker no está disponible ({type(e).__name__}): la verificación no corre en el anfitrión."
    if r.returncode != 0 or not r.stdout.strip():
        return False, "Docker no está disponible (¿está iniciado Docker Desktop?): la verificación no corre en el anfitrión."
    return True, r.stdout.strip()


def imagen_existe(imagen: str) -> bool:
    try:
        return lanzar(["docker", "image", "inspect", imagen, "--format", "{{.Id}}"], 30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def precondicion(imagenes: Sequence[str] = (IMAGEN, IMAGEN_NODE)) -> str | None:
    """Mensaje de error si Docker o alguna imagen del sandbox falta (para fallar ANTES de gastar tokens); None si todo está."""
    ok, mensaje = docker_disponible()
    if not ok:
        return mensaje
    faltan = [i for i in imagenes if not imagen_existe(i)]
    if faltan:
        return f"Faltan las imágenes del sandbox: {', '.join(faltan)}. Constrúyelas con:  {COMANDO_CONSTRUIR}"
    return None


# --- El comando ---------------------------------------------------------------------------------------------
def _choca(origen: Path, prohibido: Path) -> bool:
    return origen.is_relative_to(prohibido) or prohibido.is_relative_to(origen)


def validar_montaje(origen: Path) -> str | None:
    """Motivo por el que NO se puede montar `origen`, o None. Dentro del repo solo se monta app/ y sus subcarpetas."""
    ruta = origen.resolve()
    if not ruta.exists():
        return f"el montaje {origen} no existe"
    if "," in str(ruta):
        return f"la ruta de un montaje no puede llevar comas: {origen}"
    if ruta == RAIZ.resolve() or RAIZ.resolve().is_relative_to(ruta):
        return f"nunca se monta la raíz del repo ni uno de sus padres: {origen}"
    for prohibido in PROHIBIDOS:
        if _choca(ruta, prohibido.resolve()):
            return f"montaje prohibido (contiene o es parte de {prohibido.name}): {origen}"
    if ruta.is_relative_to(RAIZ.resolve()) and not ruta.is_relative_to(APP.resolve()):
        return f"dentro del repo solo se monta app/: {origen}"
    return None


def _validar_entorno(entorno: dict[str, str]) -> None:
    for clave, valor in entorno.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", clave) or not isinstance(valor, str):
            raise ValueError(f"variable de entorno inválida para el sandbox: {clave!r}")


def construir_comando(imagen: str, comando: Sequence[str], *, nombre: str, montajes: Sequence[Montaje] = (),
                      volumenes: Sequence[Volumen] = (), red: str = "none", limites: Limites = LIMITES_PRUEBAS,
                      entorno: dict[str, str] | None = None, usuario: str = "pwuser", directorio: str = "/work") -> list[str]:
    """El `docker run` completo. Solo -e CLAVE=valor explícitos: nada del entorno del anfitrión (sin --env-file)."""
    entorno = {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", **(entorno or {})}
    _validar_entorno(entorno)
    for m in montajes:
        motivo = validar_montaje(m.origen)
        if motivo:
            raise ValueError(motivo)
    argv = ["docker", "run", "--rm", "--name", nombre, "--pull", "never", "--init", "--read-only",
            "--tmpfs", f"/tmp:rw,nosuid,size={limites.tmp}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", usuario,
            "--memory", limites.memoria, "--memory-swap", limites.memoria, "--cpus", str(limites.cpus),
            "--pids-limit", str(limites.pids), "--network", red]
    if limites.shm:
        argv += ["--shm-size", limites.shm]
    for clave, valor in entorno.items():
        argv += ["-e", f"{clave}={valor}"]
    for m in montajes:                       # --mount (no -v): falla si la ruta no existe en vez de crearla
        argv += ["--mount", f"type=bind,source={m.origen.resolve()},target={m.destino}" + ("" if m.escritura else ",readonly")]
    for v in volumenes:
        argv += ["--mount", f"type=volume,source={v.nombre},target={v.destino}" + ("" if v.escritura else ",readonly")]
    return [*argv, "-w", directorio, imagen, *comando]


def ejecutar(imagen: str, comando: Sequence[str], *, montajes: Sequence[Montaje] = (), volumenes: Sequence[Volumen] = (),
             red: str = "none", limites: Limites = LIMITES_PRUEBAS, entorno: dict[str, str] | None = None,
             timeout: int = 600, usuario: str = "pwuser", directorio: str = "/work") -> Resultado:
    """Corre `comando` dentro de `imagen`. Docker ausente o imagen sin construir → falla; nunca corre en el anfitrión."""
    ok, mensaje = docker_disponible()
    if not ok:
        return Resultado(False, mensaje)
    if not imagen_existe(imagen):
        return Resultado(False, f"Falta la imagen del sandbox {imagen}. Constrúyela con:  {COMANDO_CONSTRUIR}")
    nombre = f"fabrica-sandbox-{secrets.token_hex(4)}"
    try:
        argv = construir_comando(imagen, comando, nombre=nombre, montajes=montajes, volumenes=volumenes, red=red,
                                 limites=limites, entorno=entorno, usuario=usuario, directorio=directorio)
    except ValueError as e:
        return Resultado(False, f"Sandbox: {e}")
    try:
        r = lanzar(argv, timeout)
    except subprocess.TimeoutExpired:
        lanzar(["docker", "kill", nombre], 30)     # matar el CLI no detiene el contenedor
        return Resultado(False, f"Sandbox: el comando superó {timeout} s y se detuvo el contenedor.", -1)
    except OSError as e:
        return Resultado(False, f"Sandbox: no se pudo lanzar Docker ({e}).")
    return Resultado(r.returncode == 0, (r.stdout + r.stderr)[-6000:], r.returncode)


# --- Carpeta de salida (fuera del repo) y red del e2e ------------------------------------------------------------
def carpeta_de_salida() -> Path:
    """Carpeta temporal FUERA del repo, escribible por el contenedor, donde deja resultados.xml."""
    carpeta = Path(tempfile.mkdtemp(prefix="fabrica_sandbox_"))
    try:
        os.chmod(carpeta, 0o777)
    except OSError:
        pass
    return carpeta


def conectar_app_a_red_e2e(servicios: Sequence[str] = ("backend", "frontend")) -> tuple[list[str], str]:
    """Crea la red interna y conecta a ella los contenedores de la app (alias = nombre del servicio).

    Devuelve (ids conectados, error). Sin Internet: la red es --internal; la app conserva su red normal.
    """
    lanzar(["docker", "network", "create", "--internal", RED_E2E], 30)       # si ya existe, falla sin consecuencias
    ids: list[str] = []
    for servicio in servicios:
        r = lanzar(["docker", "compose", "-f", str(APP / "docker-compose.yml"), "--project-directory", str(APP),
                    "ps", "-q", servicio], 60)
        contenedor = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
        if not contenedor:
            return ids, f"El servicio «{servicio}» de la app no está en ejecución: despliega la app antes del e2e."
        c = lanzar(["docker", "network", "connect", "--alias", servicio, RED_E2E, contenedor], 30)
        if c.returncode != 0 and "already exists" not in (c.stderr + c.stdout):
            return ids, f"No se pudo conectar «{servicio}» a la red {RED_E2E}: {(c.stderr or c.stdout).strip()[-300:]}"
        ids.append(contenedor)
    return ids, ""


def desconectar_app_de_red_e2e(ids: Sequence[str]) -> None:
    for contenedor in ids:
        lanzar(["docker", "network", "disconnect", RED_E2E, contenedor], 30)
