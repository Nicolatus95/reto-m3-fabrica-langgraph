"""Pruebas de hooks/seguridad.py: registros/ bloqueada para todos y auditoría que no se apaga.

El hook se copia a una estructura temporal (tmp/hooks/seguridad.py) para que su RAIZ sea tmp: la ruta del registro es
fija y no se puede redirigir con una variable de entorno, así que esta es la única forma de probarla sin tocar el
registro real del proyecto.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "seguridad.py"
SENUELO = "BANDERA" + "-DEMO"     # partido en dos: el hook también revisa lo que se escribe en este archivo


@pytest.fixture
def entorno(tmp_path):
    (tmp_path / "hooks").mkdir()
    shutil.copy(HOOK, tmp_path / "hooks" / "seguridad.py")
    (tmp_path / "registros").mkdir()
    (tmp_path / "app").mkdir()

    def ejecutar(herramienta: str, entrada: dict, defensas: str | None = None, agente: str | None = None,
                 extra: dict | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "DEFENSAS"}
        if defensas is not None:
            env["DEFENSAS"] = defensas
        env.update(extra or {})
        datos = {"tool_name": herramienta, "tool_input": entrada, **({"agent_type": agente} if agente else {})}
        return subprocess.run([sys.executable, str(tmp_path / "hooks" / "seguridad.py")], input=json.dumps(datos),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, check=False)

    def auditoria() -> list[dict]:
        ruta = tmp_path / "registros" / "auditoria.jsonl"
        return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []

    return ejecutar, auditoria, tmp_path


# --- La auditoría se escribe SIEMPRE ------------------------------------------------------------------------
def test_con_defensas_activas_se_audita_con_el_campo_defensas(entorno):
    ejecutar, auditoria, _ = entorno
    assert ejecutar("Read", {"file_path": "app/main.py"}).returncode == 0
    assert [(a["agente"], a["herramienta"], a["defensas"]) for a in auditoria()] == [("principal", "Read", "activas")]


def test_con_defensas_0_se_audita_como_apagadas(entorno):
    ejecutar, auditoria, _ = entorno
    assert ejecutar("Read", {"file_path": "app/main.py"}).returncode == 0
    assert ejecutar("Read", {"file_path": "registros/seguridad.jsonl"}, defensas="0").returncode == 0   # se apaga el bloqueo
    assert ejecutar("Bash", {"command": "cat .env"}, defensas="0", agente="desarrollador").returncode == 0
    assert [(a["agente"], a["defensas"]) for a in auditoria()] == [
        ("principal", "activas"), ("principal", "apagadas"), ("desarrollador", "apagadas")]


def test_una_llamada_bloqueada_tambien_queda_auditada(entorno):
    ejecutar, auditoria, _ = entorno
    assert ejecutar("Bash", {"command": "cat registros/seguridad.jsonl"}).returncode == 2
    assert [(a["herramienta"], a["defensas"]) for a in auditoria()] == [("Bash", "activas")]


def test_la_ruta_del_registro_no_se_configura_por_variable_de_entorno(entorno):
    ejecutar, auditoria, tmp = entorno
    ejecutar("Read", {"file_path": "app/main.py"}, extra={
        "REGISTROS": str(tmp / "otra"), "AUDITORIA": str(tmp / "otra" / "a.jsonl"), "RAIZ": str(tmp / "otra"),
        "REGISTROS_DIR": str(tmp / "otra"), "AUDITORIA_JSONL": str(tmp / "otra" / "a.jsonl")})
    assert len(auditoria()) == 1 and not (tmp / "otra").exists()


def test_la_carpeta_de_registros_se_crea_sola(entorno):
    ejecutar, auditoria, tmp = entorno
    shutil.rmtree(tmp / "registros")
    assert ejecutar("Read", {"file_path": "app/main.py"}).returncode == 0 and len(auditoria()) == 1


def test_si_no_se_puede_auditar_con_defensas_activas_se_bloquea(entorno):
    """Un error normal (exit 1) dejaría pasar la herramienta sin rastro: se falla cerrado."""
    ejecutar, _, tmp = entorno
    shutil.rmtree(tmp / "registros")
    (tmp / "registros").write_text("esto es un archivo, no una carpeta", encoding="utf-8")
    assert ejecutar("Read", {"file_path": "app/main.py"}).returncode == 2
    assert ejecutar("Read", {"file_path": "app/main.py"}, defensas="0").returncode == 0     # en clase no estorba


# --- registros/ bloqueada de forma explícita, para todos ------------------------------------------------------
@pytest.mark.parametrize("herramienta, entrada", [
    ("Read", {"file_path": "registros/seguridad.jsonl"}),
    ("Read", {"file_path": "registros/HU-01/revision.json"}),
    ("Read", {"file_path": "./registros/auditoria.jsonl"}),
    ("Read", {"file_path": "app/../registros/auditoria.jsonl"}),
    ("Glob", {"pattern": "*.jsonl", "path": "registros"}),
    ("Glob", {"pattern": "registros/**/*.json"}),
    ("Grep", {"pattern": "motivo", "path": "registros"}),
    ("Grep", {"pattern": "motivo", "path": ".", "glob": "registros/*.jsonl"}),
])
@pytest.mark.parametrize("agente", [None, "desarrollador", "triage"])
def test_leer_registros_sale_con_exit_2_para_todos(entorno, herramienta, entrada, agente):
    ejecutar, _, _ = entorno
    r = ejecutar(herramienta, entrada, agente=agente)
    assert r.returncode == 2 and "registros/ es solo para personas" in r.stderr


def test_la_ruta_absoluta_a_registros_tambien_se_bloquea(entorno):
    ejecutar, _, tmp = entorno
    assert ejecutar("Read", {"file_path": str(tmp / "registros" / "seguridad.jsonl")}).returncode == 2


@pytest.mark.parametrize("comando", [
    "cat registros/seguridad.jsonl",
    r"type .\registros\auditoria.jsonl",
    "ls ./registros",
    "CAT REGISTROS/x",
    "cd registros && ls",
    "grep -r motivo 'registros'",
    "python -c \"print(open('registros/seguridad.jsonl').read())\"",
])
def test_bash_que_nombra_registros_como_ruta_se_bloquea(entorno, comando):
    ejecutar, _, _ = entorno
    r = ejecutar("Bash", {"command": comando})
    assert r.returncode == 2 and "registros/ es solo para personas" in r.stderr
    assert ejecutar("Bash", {"command": comando}, agente="desarrollador").returncode == 2


@pytest.mark.parametrize("comando", [
    ".venv/Scripts/python -m pytest -k registro_empleado",
    "curl http://localhost:8000/empleados?registros=10",
    'curl "http://localhost:8000/empleados?x=1&registros=10"',
    "curl http://localhost:8000/empleados",
    "ls app/backend",
])
def test_bash_legitimo_no_se_bloquea(entorno, comando):
    ejecutar, _, _ = entorno
    assert ejecutar("Bash", {"command": comando}).returncode == 0


def test_lecturas_legitimas_pasan(entorno):
    ejecutar, _, _ = entorno
    for entrada in ({"file_path": "app/main.py"}, {"file_path": "docs/registros_de_clase.md"}):
        assert ejecutar("Read", entrada).returncode == 0
    assert ejecutar("Grep", {"pattern": "registros", "path": "app"}).returncode == 0     # buscar la palabra es legítimo


def test_las_defensas_anteriores_siguen_activas(entorno):
    ejecutar, _, _ = entorno
    assert ejecutar("Bash", {"command": "cat .env"}).returncode == 2
    assert ejecutar("Read", {"file_path": "../fuera.txt"}).returncode == 2
    assert ejecutar("Bash", {"command": "echo `id`"}).returncode == 2
    assert ejecutar("Write", {"file_path": "x.txt", "content": SENUELO}).returncode == 2
