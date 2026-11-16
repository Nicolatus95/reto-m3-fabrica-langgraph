"""Sesión 3 · ¿Los contenedores responden? El backend en 8000 y el frontend (con su proxy /api) en 8080."""
from verificacion import compose_seguro
from verificacion.comun import APP, correr, responde


def verificar(hu: str | None = None) -> tuple[bool, str]:
    if not (APP / "docker-compose.yml").exists():
        return False, "No existe app/docker-compose.yml"
    resultados = [responde(u, intentos=60) for u in
                  ("http://localhost:8000/api/salud", "http://localhost:8080", "http://localhost:8080/api/salud")]
    ok = all(r for r, _ in resultados)
    log = "\n".join(linea for _, linea in resultados)
    if not ok:                                         # el log de los contenedores ayuda al agente a corregir
        log += "\n\n## docker compose ps\n" + correr(["docker", "compose", "ps"], APP, timeout=60)[1]
        log += "\n\n## docker compose logs --tail 40\n" + correr(["docker", "compose", "logs", "--tail", "40"], APP, timeout=60)[1]
    return ok, log


def redesplegar() -> tuple[bool, str]:
    """Reconstruye los contenedores sin pasar por un agente (después de corregir código, sesión 4).

    Antes del `up` se revisa el docker-compose.yml (verificacion/compose_seguro.py): lo escribe un agente.
    """
    problemas = compose_seguro.problemas(APP)
    if problemas:
        return False, "El docker-compose.yml no pasa el chequeo de seguridad; no se despliega:\n- " + "\n- ".join(problemas)
    ok, log = correr(["docker", "compose", "up", "-d", "--build"], APP)
    return verificar() if ok else (False, log)
