"""Construye las imágenes del sandbox, UNA vez y con nombre fijo:  python -m verificacion imagen_sandbox [reconstruir]

- fabrica-sandbox:1       desde sandbox/Dockerfile       (pytest, pytest-playwright, httpx y las dependencias del backend)
- fabrica-sandbox-node:1  desde sandbox/Dockerfile.node  (node, para el front-end)
Descarga imágenes base (Playwright ~2 GB, node ~0.2 GB): por eso es un comando explícito y no algo que una verificación
haga sola. Si las imágenes ya existen no hace nada, salvo que se pida «reconstruir».
"""
import subprocess

from verificacion import sandbox
from verificacion.comun import RAIZ

IMAGENES = [(sandbox.IMAGEN, "Dockerfile"), (sandbox.IMAGEN_NODE, "Dockerfile.node")]


def tamano_mb(imagen: str) -> str:
    r = sandbox.lanzar(["docker", "image", "inspect", imagen, "--format", "{{.Size}}"], 30)
    try:
        return f"{int(r.stdout.strip()) / 1_000_000:,.0f} MB"
    except ValueError:
        return "?"


def verificar(hu: str | None = None) -> tuple[bool, str]:
    """`hu` aquí es una opción: «reconstruir» fuerza la construcción aunque la imagen exista."""
    disponible, mensaje = sandbox.docker_disponible()
    if not disponible:
        return False, mensaje
    lineas = []
    for imagen, dockerfile in IMAGENES:
        if sandbox.imagen_existe(imagen) and hu != "reconstruir":
            lineas.append(f"{imagen}: ya existe ({tamano_mb(imagen)})")
            continue
        try:
            r = sandbox.lanzar(["docker", "build", "-t", imagen, "-f", str(RAIZ / "sandbox" / dockerfile),
                                str(RAIZ / "sandbox")], 1800)
        except subprocess.TimeoutExpired:
            return False, f"{imagen}: la construcción superó 30 minutos"
        if r.returncode != 0:
            return False, f"{imagen}: la construcción falló\n{(r.stdout + r.stderr)[-3000:]}"
        lineas.append(f"{imagen}: construida ({tamano_mb(imagen)})")
    return True, "\n".join(lineas)
