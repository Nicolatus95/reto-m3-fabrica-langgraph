"""Pruebas del sandbox (verificacion/sandbox.py y las verificaciones que lo usan) con un doble de Docker: sin Docker real.

Se comprueba el COMANDO que se lanzaría: flags de seguridad, montajes mínimos, entorno vacío del anfitrión, la red de cada
caso, y que sin Docker la verificación falla en lugar de correr en el anfitrión.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

import verificacion.app
import verificacion.compose_seguro as compose_seguro
import verificacion.e2e
import verificacion.imagen_sandbox
import verificacion.pruebas
from hooks import rol
from hooks.roles import ROLES
from verificacion import sandbox
from verificacion.comun import APP, RAIZ

PLAN = {"historia": "HU-01", "casos": [{"id": "CP-01", "escenario": "x", "nivel": "api", "precondiciones": [],
                                         "pasos": [], "datos": {}, "resultado_esperado": "ok"}]}


def completado(codigo: int = 0, salida: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], codigo, stdout=salida, stderr="")


def valor_de(argv: list[str], bandera: str) -> str:
    return argv[argv.index(bandera) + 1]


class DockerFalso:
    """Doble de sandbox.lanzar: registra cada llamada a Docker y responde según lo configurado."""

    def __init__(self):
        self.llamadas: list[list[str]] = []
        self.disponible = True
        self.imagenes = {sandbox.IMAGEN, sandbox.IMAGEN_NODE}
        self.codigos_run: list[int] = []            # códigos de salida de los `docker run` sucesivos (0 si se acaban)
        self.salida_run = "ok"
        self.agota_el_tiempo = False
        self.servicios = {"backend": "id-back", "frontend": "id-front"}
        self.al_correr = None                       # callback(argv) en cada `docker run`
        self.config = None                          # lo que devuelve `docker compose config --format json` (None = falla)

    def __call__(self, argv: list[str], timeout: int):
        self.llamadas.append(argv)
        if argv[:2] == ["docker", "info"]:
            return completado(0 if self.disponible else 1, "29.9.2\n" if self.disponible else "")
        if argv[:3] == ["docker", "image", "inspect"]:
            return completado(0 if argv[3] in self.imagenes else 1, "sha256:abc")
        if argv[:2] == ["docker", "run"]:
            if self.agota_el_tiempo:
                raise subprocess.TimeoutExpired(argv, timeout)
            if self.al_correr:
                self.al_correr(argv)
            return completado(self.codigos_run.pop(0) if self.codigos_run else 0, self.salida_run)
        if argv[:2] == ["docker", "compose"] and "config" in argv:
            return completado(0, json.dumps(self.config)) if self.config is not None else completado(1, "")
        if "ps" in argv and "-q" in argv:
            return completado(0, self.servicios.get(argv[-1], "") + "\n")
        return completado(0, "")

    def corridas(self) -> list[list[str]]:
        return [a for a in self.llamadas if a[:2] == ["docker", "run"]]


@pytest.fixture
def docker(monkeypatch):
    falso = DockerFalso()
    monkeypatch.setattr(sandbox, "lanzar", falso)
    monkeypatch.setattr(compose_seguro, "lanzar", falso)
    return falso


@pytest.fixture
def sin_anfitrion(monkeypatch):
    """Cualquier subproceso lanzado en el anfitrión (uvicorn, pytest, npm…) revienta la prueba."""
    def prohibido(*args, **kwargs):
        raise AssertionError(f"se intentó correr algo en el anfitrión: {args[:1]}")
    monkeypatch.setattr(subprocess, "run", prohibido)
    monkeypatch.setattr(subprocess, "Popen", prohibido)


@pytest.fixture
def salida(monkeypatch, tmp_path):
    """salida/ temporal con casos_prueba.json de HU-01 (los ids deben aparecer en app/tests)."""
    carpeta = tmp_path / "salida"
    (carpeta / "HU-01").mkdir(parents=True)
    (carpeta / "HU-01" / "casos_prueba.json").write_text(json.dumps(PLAN), encoding="utf-8")
    monkeypatch.setattr(verificacion.pruebas, "SALIDA", carpeta)
    monkeypatch.setattr(verificacion.e2e, "SALIDA", carpeta)
    return carpeta


# --- El comando: flags de seguridad ---------------------------------------------------------------------------
def comando_basico(**kwargs) -> list[str]:
    return sandbox.construir_comando(sandbox.IMAGEN, ["python", "-V"], nombre="fabrica-sandbox-x",
                                     montajes=[sandbox.Montaje(APP / "tests", "/work/tests")], **kwargs)


def test_el_comando_lleva_todos_los_flags_de_seguridad():
    argv = comando_basico()
    assert argv[:3] == ["docker", "run", "--rm"] and "--read-only" in argv and "--init" in argv
    assert valor_de(argv, "--cap-drop") == "ALL" and valor_de(argv, "--security-opt") == "no-new-privileges"
    assert valor_de(argv, "--user") == "pwuser" and valor_de(argv, "--pull") == "never"
    assert valor_de(argv, "--memory") == valor_de(argv, "--memory-swap")             # sin swap
    assert float(valor_de(argv, "--cpus")) > 0 and int(valor_de(argv, "--pids-limit")) > 0
    assert re.fullmatch(r"/tmp:rw,nosuid,size=\d+[mg]", valor_de(argv, "--tmpfs"))
    assert valor_de(argv, "--network") == "none" and valor_de(argv, "-w") == "/work"
    assert argv[-3:] == [sandbox.IMAGEN, "python", "-V"]


def test_el_comando_no_trae_nada_peligroso():
    argv = comando_basico()
    prohibidas = {"--privileged", "--env-file", "--volume", "-v", "--cap-add", "--pid", "--ipc", "--device", "--userns",
                  "--uts", "--cgroupns", "--gpus"}
    assert not prohibidas & set(argv)
    assert valor_de(argv, "--network") != "host" and "docker.sock" not in " ".join(argv)
    assert all("unconfined" not in a for a in argv)


def test_el_entorno_del_anfitrion_no_pasa(monkeypatch):
    monkeypatch.setenv("SECRETO_DEL_ANFITRION", "valor-que-no-debe-salir")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-no")
    argv = comando_basico(entorno={"URL_API": "http://backend:8000"})
    assert "valor-que-no-debe-salir" not in " ".join(argv) and "sk-no" not in " ".join(argv)
    variables = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert sorted(variables) == ["HOME=/tmp", "PYTHONDONTWRITEBYTECODE=1", "URL_API=http://backend:8000"]
    assert all("=" in v for v in variables)                      # nunca -e CLAVE sin valor (copiaría el del anfitrión)


def test_una_variable_de_entorno_invalida_se_rechaza():
    with pytest.raises(ValueError):
        comando_basico(entorno={"A B": "x"})


def test_los_montajes_de_solo_lectura_llevan_readonly_y_el_de_salida_no(tmp_path):
    argv = sandbox.construir_comando(sandbox.IMAGEN, ["x"], nombre="n", montajes=[
        sandbox.Montaje(APP / "tests", "/work/tests"), sandbox.Montaje(tmp_path, "/out", escritura=True)])
    montajes = [argv[i + 1] for i, a in enumerate(argv) if a == "--mount"]
    assert len(montajes) == 2
    assert montajes[0].endswith("target=/work/tests,readonly") and montajes[1].endswith("target=/out")
    assert "readonly" not in montajes[1] and all(m.startswith("type=bind,source=") for m in montajes)


# --- Montajes prohibidos ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("ruta", [RAIZ, RAIZ.parent, RAIZ / ".venv", RAIZ / "registros", RAIZ / "secretos_demo.txt",
                                  RAIZ / "hooks", RAIZ / ".claude", RAIZ / "salida", RAIZ / "docs", RAIZ / "flujos",
                                  Path(RAIZ.anchor)])
def test_nunca_se_monta_el_repo_ni_sus_secretos(ruta):
    if ruta.exists():                                   # registros/ solo existe en máquinas que ya corrieron la fábrica
        assert sandbox.validar_montaje(ruta), ruta
        with pytest.raises(ValueError):
            sandbox.construir_comando(sandbox.IMAGEN, ["x"], nombre="n", montajes=[sandbox.Montaje(ruta, "/x")])


def test_se_pueden_montar_las_carpetas_de_app_y_una_salida_temporal(tmp_path):
    for ruta in (APP / "tests", APP / "backend", APP / "frontend", tmp_path):
        assert sandbox.validar_montaje(ruta) is None, ruta


def test_un_montaje_que_no_existe_se_rechaza(tmp_path):
    assert "no existe" in sandbox.validar_montaje(tmp_path / "nada")


def test_ejecutar_con_un_montaje_prohibido_no_lanza_docker(docker):
    r = sandbox.ejecutar(sandbox.IMAGEN, ["x"], montajes=[sandbox.Montaje(RAIZ, "/repo")])
    assert not r.ok and "Sandbox:" in r.salida and not docker.corridas()


# --- Docker ausente: falla cerrado ----------------------------------------------------------------------------
def test_sin_docker_ejecutar_falla_y_no_corre_nada(docker, sin_anfitrion):
    docker.disponible = False
    r = sandbox.ejecutar(sandbox.IMAGEN, ["x"])
    assert not r.ok and "Docker no está disponible" in r.salida and not docker.corridas()


def test_sin_la_imagen_falla_con_el_comando_para_construirla(docker):
    docker.imagenes = set()
    r = sandbox.ejecutar(sandbox.IMAGEN, ["x"])
    assert not r.ok and sandbox.COMANDO_CONSTRUIR in r.salida and not docker.corridas()


@pytest.mark.parametrize("verificacion_", [verificacion.pruebas.verificar, verificacion.app.verificar,
                                           verificacion.e2e.verificar])
def test_cada_verificacion_falla_sin_docker_y_no_toca_el_anfitrion(docker, sin_anfitrion, salida, verificacion_):
    docker.disponible = False
    ok, log = verificacion_("HU-01")
    assert not ok and "Docker no está disponible" in log and not docker.corridas()


def test_si_docker_no_esta_instalado_tambien_falla(monkeypatch, sin_anfitrion):
    def no_existe(argv, timeout):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(sandbox, "lanzar", no_existe)
    ok, mensaje = sandbox.docker_disponible()
    assert not ok and "no corre en el anfitrión" in mensaje


def test_un_tiempo_agotado_detiene_el_contenedor(docker):
    docker.agota_el_tiempo = True
    r = sandbox.ejecutar(sandbox.IMAGEN, ["x"], timeout=5)
    assert not r.ok and "superó 5 s" in r.salida
    nombre = [a for a in docker.llamadas if a[:2] == ["docker", "kill"]]
    assert len(nombre) == 1 and nombre[0][2].startswith("fabrica-sandbox-")


def test_precondicion(docker):
    assert sandbox.precondicion() is None
    docker.imagenes = {sandbox.IMAGEN}
    mensaje = sandbox.precondicion()
    assert sandbox.IMAGEN_NODE in mensaje and sandbox.IMAGEN not in mensaje and sandbox.COMANDO_CONSTRUIR in mensaje
    docker.disponible = False
    assert "Docker no está disponible" in sandbox.precondicion()


# --- La red de cada caso ---------------------------------------------------------------------------------------
def test_pruebas_collect_only_sin_red_y_con_app_tests_en_solo_lectura(docker, sin_anfitrion, salida):
    ok, _ = verificacion.pruebas.verificar("HU-01")
    assert ok
    (argv,) = docker.corridas()
    assert valor_de(argv, "--network") == "none" and "target=/work/tests,readonly" in " ".join(argv)
    assert argv[argv.index(sandbox.IMAGEN) + 1:][:6] == ["python", "-m", "pytest", "tests", "--collect-only", "-q"]
    fuentes = [m.split("source=")[1].split(",")[0] for m in argv if m.startswith("type=bind")]
    assert fuentes == [str((APP / "tests").resolve())]                    # solo app/tests, nunca la raíz del repo


def test_pruebas_sigue_comprobando_la_trazabilidad(docker, salida):
    plan = {**PLAN, "casos": [{**PLAN["casos"][0], "id": "CP-98"}]}
    (salida / "HU-01" / "casos_prueba.json").write_text(json.dumps(plan), encoding="utf-8")
    ok, log = verificacion.pruebas.verificar("HU-01")
    assert not ok and "Casos sin test: CP-98" in log


def test_backend_sin_red_con_la_carpeta_en_solo_lectura(docker, sin_anfitrion):
    ok, _ = verificacion.app.verificar_backend()
    assert ok
    (argv,) = docker.corridas()
    assert valor_de(argv, "--network") == "none" and argv[-2:] == ["python", "/opt/verificar_backend.py"]
    assert any(m.endswith("target=/src,readonly") for m in argv)


def test_frontend_en_dos_fases_la_primera_con_red_y_sin_scripts_y_la_segunda_sin_red(docker, sin_anfitrion):
    ok, _ = verificacion.app.verificar_frontend()
    assert ok
    fase1, fase2 = docker.corridas()
    assert valor_de(fase1, "--network") == "bridge" and "npm ci --ignore-scripts" in fase1[-1]
    assert valor_de(fase2, "--network") == "none" and "npm run build" in fase2[-1]
    for argv in (fase1, fase2):
        assert valor_de(argv, "--user") == "node" and argv[argv.index("--cap-drop") + 1] == "ALL"
        assert any(m.endswith("target=/in,readonly") for m in argv)                 # la fuente nunca es escribible
        assert any(m.startswith("type=volume,source=fabrica-npm-") for m in argv)
    assert [a for a in docker.llamadas if a[:3] == ["docker", "volume", "rm"]]        # el volumen temporal se borra


def test_si_la_fase_1_falla_no_hay_fase_2_y_el_volumen_se_borra(docker, sin_anfitrion):
    docker.codigos_run = [1]
    ok, log = verificacion.app.verificar_frontend()
    assert not ok and len(docker.corridas()) == 1 and "npm ci" in log
    assert [a for a in docker.llamadas if a[:3] == ["docker", "volume", "rm"]]


def test_e2e_en_la_red_interna_con_las_urls_del_compose_y_sin_entorno_del_anfitrion(docker, sin_anfitrion, salida,
                                                                                    monkeypatch):
    monkeypatch.setenv("SECRETO_DEL_ANFITRION", "no")

    def escribir_resultados(argv):                              # el contenedor deja resultados.xml en /out
        fuente = next(m for m in argv if m.endswith("target=/out")).split("source=")[1].split(",")[0]
        (Path(fuente) / "resultados.xml").write_text(
            '<testsuites><testsuite><testcase classname="tests.api.test_x" name="test_a"/>'
            '<testcase classname="tests.api.test_x" name="test_b"><failure message="boom"/></testcase>'
            '</testsuite></testsuites>', encoding="utf-8")

    docker.al_correr = escribir_resultados
    docker.codigos_run = [1]
    docker.salida_run = "1 failed, 1 passed in 3s"
    ok, log = verificacion.e2e.verificar("HU-01")
    assert not ok and "1 failed, 1 passed" in log and "tests.api.test_x::test_b" in log and "boom" in log
    (argv,) = docker.corridas()
    assert valor_de(argv, "--network") == sandbox.RED_E2E and "SECRETO_DEL_ANFITRION" not in " ".join(argv)
    variables = {argv[i + 1] for i, a in enumerate(argv) if a == "-e"}
    assert {"URL_API=http://backend:8000", "URL_WEB=http://frontend"} <= variables
    assert any(m.endswith("target=/work/tests,readonly") for m in argv)
    assert (salida / "HU-01" / "resultados.xml").exists() and "test_b" in (salida / "HU-01" / "fallos.md").read_text(encoding="utf-8")
    assert not [a for a in argv if a.startswith("type=bind") and "target=/out" in a and "readonly" in a]


def test_e2e_crea_la_red_interna_conecta_la_app_con_alias_y_la_desconecta(docker, salida):
    verificacion.e2e.verificar("HU-01")
    crear = [a for a in docker.llamadas if a[:3] == ["docker", "network", "create"]]
    assert crear == [["docker", "network", "create", "--internal", sandbox.RED_E2E]]           # sin salida a Internet
    conectar = [a for a in docker.llamadas if a[:3] == ["docker", "network", "connect"]]
    assert conectar == [["docker", "network", "connect", "--alias", "backend", sandbox.RED_E2E, "id-back"],
                        ["docker", "network", "connect", "--alias", "frontend", sandbox.RED_E2E, "id-front"]]
    desconectar = [a for a in docker.llamadas if a[:3] == ["docker", "network", "disconnect"]]
    assert {a[-1] for a in desconectar} == {"id-back", "id-front"}


def test_e2e_sin_la_app_desplegada_falla_sin_correr_las_pruebas(docker, salida):
    docker.servicios = {}
    ok, log = verificacion.e2e.verificar("HU-01")
    assert not ok and "no está en ejecución" in log and not docker.corridas()


def test_e2e_no_usa_un_resultado_viejo(docker, salida):
    viejo = salida / "HU-01" / "resultados.xml"
    viejo.write_text('<testsuites><testsuite><testcase classname="a" name="viejo"><failure message="x"/></testcase>'
                     '</testsuite></testsuites>', encoding="utf-8")
    docker.codigos_run = [1]
    ok, log = verificacion.e2e.verificar("HU-01")                # el sandbox no dejó resultados.xml
    assert not ok and "viejo" not in log and not viejo.exists()


# --- Imágenes -----------------------------------------------------------------------------------------------------
def test_imagen_sandbox_construye_solo_lo_que_falta(docker):
    docker.imagenes = {sandbox.IMAGEN}
    ok, log = verificacion.imagen_sandbox.verificar()
    construidas = [a for a in docker.llamadas if a[:2] == ["docker", "build"]]
    assert ok and len(construidas) == 1 and construidas[0][3] == sandbox.IMAGEN_NODE
    assert construidas[0][construidas[0].index("-f") + 1].endswith("Dockerfile.node")
    assert f"{sandbox.IMAGEN}: ya existe" in log


def test_imagen_sandbox_sin_docker_falla(docker):
    docker.disponible = False
    assert not verificacion.imagen_sandbox.verificar()[0]


def test_los_dockerfiles_fijan_versiones_y_no_corren_como_root():
    dockerfile = (RAIZ / "sandbox" / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith("# ") and "FROM mcr.microsoft.com/playwright/python:v1.65.2-noble" in dockerfile
    for paquete in ("pytest==", "pytest-playwright==", "httpx==", "fastapi==", "uvicorn==", "sqlalchemy==", "pydantic=="):
        assert paquete in dockerfile
    assert "USER pwuser" in dockerfile and "USER node" in (RAIZ / "sandbox" / "Dockerfile.node").read_text(encoding="utf-8")


# --- compose seguro --------------------------------------------------------------------------------------------------
def compose_base() -> dict:
    return {"services": {
        "backend": {"build": {"context": str(APP / "backend")},
                    "volumes": [{"type": "bind", "source": str(APP / "backend" / "datos"), "target": "/app/datos"}]},
        "frontend": {"build": {"context": str(APP / "frontend")}}}}


def test_el_compose_actual_es_seguro():
    assert compose_seguro.evaluar(compose_base(), (APP / "docker-compose.yml").read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("cambio, esperado", [
    ({"privileged": True}, "privileged"),
    ({"network_mode": "host"}, "network_mode: host"),
    ({"network_mode": "container:otro"}, "network_mode"),
    ({"pid": "host"}, "pid: host"),
    ({"ipc": "host"}, "ipc: host"),
    ({"uts": "host"}, "uts: host"),
    ({"userns_mode": "host"}, "userns_mode"),
    ({"cap_add": ["SYS_ADMIN"]}, "cap_add"),
    ({"devices": ["/dev/sda:/dev/sda"]}, "devices"),
    ({"security_opt": ["seccomp=unconfined"]}, "security_opt"),
    ({"volumes": [{"type": "bind", "source": "C:\\", "target": "/host"}]}, "fuera de app/"),
    ({"volumes": [{"type": "bind", "source": str(RAIZ), "target": "/repo"}]}, "fuera de app/"),
    ({"volumes": [{"type": "bind", "source": str(RAIZ / "secretos_demo.txt"), "target": "/s"}]}, "fuera de app/"),
    ({"volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}]}, "socket de Docker"),
    ({"volumes": [{"type": "npipe", "source": "\\\\.\\pipe\\docker_engine", "target": "\\\\.\\pipe\\docker_engine"}]}, "socket"),
    ({"build": {"context": str(RAIZ)}}, "contexto de build"),
    ({"build": {"context": str(APP / "backend"), "additional_contexts": {"x": str(RAIZ / ".venv")}}}, "contexto de build"),
])
def test_un_compose_peligroso_se_rechaza(cambio, esperado):
    config = compose_base()
    config["services"]["backend"] = {**config["services"]["backend"], **cambio}
    problemas = compose_seguro.evaluar(config, "services:\n")
    assert problemas and any(esperado in p for p in problemas), problemas


def test_volumenes_y_secretos_de_nivel_superior_se_rechazan():
    config = {**compose_base(), "volumes": {"v": {"driver_opts": {"type": "none", "o": "bind", "device": "C:\\"}}},
              "secrets": {"s": {"file": "C:\\secretos.txt"}}}
    problemas = compose_seguro.evaluar(config, "")
    assert any("driver_opts" in p for p in problemas) and any("secrets" in p for p in problemas)


@pytest.mark.parametrize("texto, esperado", [("environment:\n  K: ${ANTHROPIC_API_KEY}\n", "interpolación"),
                                              ("    env_file: ../../.env\n", "env_file"),
                                              ("include:\n  - ../otro.yml\n", "include"),
                                              ("    extends:\n      file: x.yml\n", "extends")])
def test_el_texto_con_interpolacion_o_archivos_externos_se_rechaza(texto, esperado):
    assert any(esperado in p for p in compose_seguro.evaluar(compose_base(), texto))


def test_problemas_normaliza_con_docker_compose_config(docker):
    docker.config = compose_base()
    assert compose_seguro.problemas() == []
    assert any(a[:2] == ["docker", "compose"] and "config" in a and "json" in a for a in docker.llamadas)


def test_problemas_falla_cerrado_si_docker_no_responde(monkeypatch):
    monkeypatch.setattr(compose_seguro, "lanzar", lambda argv, t: completado(1, ""))
    assert any("docker compose config falló" in p for p in compose_seguro.problemas())

    def explota(argv, t):
        raise subprocess.TimeoutExpired(argv, t)
    monkeypatch.setattr(compose_seguro, "lanzar", explota)
    assert any("no se despliega" in p for p in compose_seguro.problemas())


def test_redesplegar_no_hace_up_si_el_compose_es_inseguro(monkeypatch):
    import verificacion.despliegue as despliegue
    llamadas = []
    monkeypatch.setattr(despliegue.compose_seguro, "problemas", lambda app: ["servicio «x»: privileged"])
    monkeypatch.setattr(despliegue, "correr", lambda *a, **k: llamadas.append(a) or (True, ""))
    ok, log = despliegue.redesplegar()
    assert not ok and "privileged" in log and not llamadas


# --- Roles y hook ------------------------------------------------------------------------------------------------
def bash(agente: str, comando: str) -> None:
    rol.revisar(agente, "Bash", {"command": comando})


def test_ningun_rol_conserva_pytest_en_el_anfitrion():
    for nombre, r in ROLES.items():
        assert not any("pytest" in p for p in r.programas), nombre
    assert ".venv/Scripts/python -m verificacion app" in ROLES["desarrollador"].programas
    assert ROLES["automatizador"].programas == {"cd", "ls", ".venv/Scripts/python -m verificacion pruebas"}
    assert not any("e2e" in p for p in ROLES["automatizador"].programas)         # e2e es el nodo del grafo, no del agente


def test_el_automatizador_corre_la_verificacion_pero_no_pytest():
    bash("automatizador", ".venv/Scripts/python -m verificacion pruebas HU-01")
    with pytest.raises(SystemExit):
        bash("automatizador", ".venv/Scripts/python -m pytest app/tests --collect-only")
    with pytest.raises(SystemExit):
        bash("automatizador", ".venv/Scripts/python -m verificacion e2e HU-01")


def test_el_desarrollador_corre_la_verificacion_pero_no_pytest():
    bash("desarrollador", ".venv/Scripts/python -m verificacion app")
    with pytest.raises(SystemExit):
        bash("desarrollador", ".venv/Scripts/python -m pytest")


@pytest.mark.parametrize("comando", ["docker run --rm -v C:\\:/host alpine sh", "docker compose run backend sh",
                                     "docker compose -f otro.yml up", "docker exec x sh", "docker build .",
                                     "docker compose down", "docker"])
def test_despliegue_no_puede_usar_docker_run_ni_otros_subcomandos(comando):
    with pytest.raises(SystemExit):
        bash("despliegue", comando)


def test_despliegue_puede_ver_el_estado_y_los_logs():
    for comando in ("docker compose ps", "docker compose logs --tail 40", "curl -s http://localhost:8000/api/salud", "sleep 5"):
        bash("despliegue", comando)


def test_docker_compose_up_del_agente_pasa_por_el_chequeo(monkeypatch):
    revisados = []
    monkeypatch.setattr(compose_seguro, "problemas", lambda app=APP: revisados.append(1) or [])
    bash("despliegue", "cd app && docker compose up -d --build")
    assert revisados == [1]
    monkeypatch.setattr(compose_seguro, "problemas", lambda app=APP: ["servicio «backend»: privileged"])
    with pytest.raises(SystemExit):
        bash("despliegue", "cd app && docker compose up -d --build")


def test_docker_compose_up_se_bloquea_si_el_chequeo_no_puede_correr(docker):
    docker.config = None                                # `docker compose config` falla: no se despliega
    with pytest.raises(SystemExit):
        bash("despliegue", "docker compose up -d")


def test_ningun_rol_puede_escribir_el_sandbox_ni_las_verificaciones():
    for nombre, r in ROLES.items():
        for ruta in ("sandbox/Dockerfile", "sandbox/Dockerfile.node", "sandbox/verificar_backend.py",
                     "verificacion/sandbox.py", "verificacion/app.py", "hooks/roles.py", "hooks/rol.py"):
            assert not rol.permitida(ruta, r.escribe), (nombre, ruta)
