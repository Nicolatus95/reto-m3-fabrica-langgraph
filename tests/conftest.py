"""Utilidades compartidas de las pruebas: un repositorio git temporal con la forma de app/."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def _git(ruta: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.name=prueba", "-c", "user.email=prueba@example.com",
                        "-c", "commit.gpgsign=false", *args], cwd=ruta, capture_output=True, text=True,
                       encoding="utf-8", check=True)
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """Repo git con un commit base: app/backend/heredado.py (con un F401 ya existente) y contexto/ de ejemplo."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "app" / "backend").mkdir(parents=True)
    (tmp_path / "contexto").mkdir()
    (tmp_path / "app" / "backend" / "heredado.py").write_text("import os\n\nx = 1\n", encoding="utf-8")
    (tmp_path / "contexto" / "reglas_negocio.md").write_text("REGLAS-DE-EJEMPLO\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return SimpleNamespace(ruta=tmp_path, base=_git(tmp_path, "rev-parse", "HEAD"),
                           git=lambda *a: _git(tmp_path, *a))
