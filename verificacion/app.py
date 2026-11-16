"""Sesión 2 · ¿La app que escribió el desarrollador funciona? Lo decide el código, no el agente.

- Backend: arranca y `GET /api/salud` debe responder.
- Frontend: `npm run build` debe terminar sin errores.

Todo corre en el sandbox (verificacion/sandbox.py), nunca en el anfitrión; sin Docker, falla.
- Backend: sin red; sandbox/verificar_backend.py arranca uvicorn dentro del contenedor y sondea por loopback.
- Frontend en dos fases, con un volumen temporal de Docker para node_modules:
    1. `npm ci --ignore-scripts` (CON red, la opción mínima: npm necesita el registro; sin scripts de ciclo de vida, así
       ningún paquete ejecuta código al instalarse);
    2. `npm run build` SIN red, con la fuente en solo lectura copiada a /tmp.
"""
import secrets

from verificacion import sandbox
from verificacion.comun import APP

CONSTRUIR = ("mkdir /tmp/app && cd /in && tar cf - --exclude=./node_modules --exclude=./dist . | tar xf - -C /tmp/app "
             "&& ln -s /deps/node_modules /tmp/app/node_modules && cd /tmp/app && npm run build")


def verificar_backend() -> tuple[bool, str]:
    if not (APP / "backend" / "main.py").exists():
        return False, "No existe app/backend/main.py"
    r = sandbox.ejecutar(sandbox.IMAGEN, ["python", "/opt/verificar_backend.py"],
                         montajes=[sandbox.Montaje(APP / "backend", "/src")], red="none",
                         limites=sandbox.LIMITES_BACKEND, timeout=120)
    return r.ok, r.salida


def verificar_frontend() -> tuple[bool, str]:
    carpeta = APP / "frontend"
    if not (carpeta / "package.json").exists():
        return False, "No existe app/frontend/package.json"
    instalar = "npm ci" if (carpeta / "package-lock.json").exists() else "npm install"
    volumen = f"fabrica-npm-{secrets.token_hex(4)}"
    entrada = sandbox.Montaje(carpeta, "/in")
    nodos = sandbox.Volumen(volumen, "/deps")
    try:
        fase1 = sandbox.ejecutar(
            sandbox.IMAGEN_NODE, ["sh", "-c", f"cp /in/package.json /deps/ && (cp /in/package-lock.json /deps/ 2>/dev/null; true) "
                                              f"&& cd /deps && {instalar} --ignore-scripts --no-audit --no-fund"],
            montajes=[entrada], volumenes=[nodos], red="bridge", limites=sandbox.LIMITES_NODE, timeout=600,
            usuario="node", directorio="/deps")
        if not fase1.ok:
            return False, f"## {instalar} (sandbox, con red)\n{fase1.salida}"
        fase2 = sandbox.ejecutar(sandbox.IMAGEN_NODE, ["sh", "-c", CONSTRUIR], montajes=[entrada], volumenes=[nodos],
                                 red="none", limites=sandbox.LIMITES_NODE, timeout=600, usuario="node", directorio="/deps")
        return fase2.ok, fase2.salida
    finally:
        sandbox.lanzar(["docker", "volume", "rm", "-f", volumen], 30)


def verificar(hu: str | None = None) -> tuple[bool, str]:
    ok_b, log_b = verificar_backend()
    ok_f, log_f = verificar_frontend()
    return ok_b and ok_f, f"## Backend\n{log_b}\n\n## Frontend\n{log_f}"
