"""Sesión 3 · ¿Las pruebas que escribió el automatizador se pueden recolectar y cubren cada caso?

Trazabilidad: cada id de salida/HU-xx/casos_prueba.json (CP-01, CP-02...) debe aparecer en algún test.
No ejecuta las pruebas contra la app: eso es la verificación e2e (sesión 4).

`pytest --collect-only` IMPORTA conftest.py y cada módulo de prueba (código del agente): corre en el sandbox, sin red,
con app/tests montada en solo lectura. Si no hay Docker, falla (nunca corre en el anfitrión).
"""
from validadores.contratos import PlanPruebas
from verificacion import sandbox
from verificacion.comun import APP, SALIDA


def verificar(hu: str | None = None) -> tuple[bool, str]:
    if not hu:
        return False, "Indica la historia: python -m verificacion pruebas HU-01"
    casos = SALIDA / hu / "casos_prueba.json"
    if not casos.exists():
        return False, f"No existe {casos.relative_to(SALIDA.parent)}"
    r = sandbox.ejecutar(sandbox.IMAGEN, ["python", "-m", "pytest", "tests", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         montajes=[sandbox.Montaje(APP / "tests", "/work/tests")], red="none",
                         limites=sandbox.LIMITES_PRUEBAS, timeout=120)
    if not r.ok:
        return False, r.salida
    ids = [c.id for c in PlanPruebas.model_validate_json(casos.read_text(encoding="utf-8")).casos]
    texto = "".join(p.read_text(encoding="utf-8") for p in (APP / "tests").rglob("test_*.py"))
    faltan = [i for i in ids if i not in texto]
    return not faltan, r.salida if not faltan else f"Casos sin test: {', '.join(faltan)}"
