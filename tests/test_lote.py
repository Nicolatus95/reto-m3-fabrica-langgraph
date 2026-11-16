"""Pruebas del lote (flujos/lote.py): dobles deterministas, sin modelo, sin Docker y sin costo.

`nodo_filtrar` corre su lógica real sobre los dobles de `EnsayoLote`; aquí se prueba el reparto con `Send`, el
aislamiento por historia, que el motivo no salga de registros/ y que `registrar_seguridad` aguante varios hilos.
"""
import contextlib
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from flujos import fabrica, lote
from flujos.lote import (
    FALLA,
    MOTIVO_ENSAYO,
    OK,
    SIN_FILTRAR,
    EnsayoLote,
    config_lote,
    construir_lote,
    escribir_reporte,
    main,
    reporte_md,
    validar_historias,
)


@pytest.fixture
def raiz(tmp_path):
    """Una raíz falsa con historias/ (la validación de rutas la usa) y los nombres que activan los dobles."""
    carpeta = tmp_path / "historias"
    carpeta.mkdir()
    for nombre in ("HU-01-uno", "HU-02-dos", "HU-03-tres", "HU-04-cuatro", "HU-05-cinco", "HU-06-seis",
                   "HU-07-explota", "HU-08-infra", "HU-98-invalida", "HU-99-envenenada"):
        (carpeta / f"{nombre}.md").write_text("contenido que el orquestador nunca lee\n", encoding="utf-8")
    (carpeta / "backlog.md").write_text("# backlog\n", encoding="utf-8")
    return tmp_path


def correr(tmp_path, historias, **kw):
    """Corre el lote con el doble; devuelve (valores finales, ensayo, ruta de lote.sqlite)."""
    ensayo = EnsayoLote(tmp_path / "salida", **kw)
    ensayo.salida.mkdir(parents=True, exist_ok=True)
    ruta_db = ensayo.salida / "lote.sqlite"
    conexion = sqlite3.connect(ruta_db, check_same_thread=False)
    try:
        app = construir_lote(ensayo.servicios(), SqliteSaver(conexion), espera=0.0)
        valores = app.invoke({"historias": historias, "resultados": [], "costo_usd": 0.0, "bitacora": []},
                             config_lote("lote-prueba"))
    finally:
        conexion.close()
    return valores, ensayo, ruta_db


def hus(*numeros):
    return [f"historias/HU-{n:02d}-x.md" for n in numeros]


@pytest.mark.parametrize("n", [1, 3, 5])
def test_n_historias_son_n_ramas_y_n_resultados(tmp_path, n):
    valores, ensayo, _ = correr(tmp_path, hus(*range(1, n + 1)))
    assert sorted(ensayo.llamadas) == [f"HU-{i:02d}" for i in range(1, n + 1)]      # una rama por historia
    assert len(valores["resultados"]) == n
    assert all(r["estado"] == OK for r in valores["resultados"])


def test_el_reporte_sale_ordenado_por_hu(tmp_path):
    valores, _, _ = correr(tmp_path, hus(5, 1, 3, 2, 4))
    texto = reporte_md(valores["resultados"], valores["costo_usd"], "20260101-000000")
    posiciones = [texto.index(f"| HU-0{i} |") for i in range(1, 6)]
    assert posiciones == sorted(posiciones)
    assert texto.count("python -m flujos.fabrica") == 5      # el comando siguiente, por cada «ok»
    assert "python -m flujos.fabrica historias/HU-03-x.md" in texto


def test_una_bloqueada_y_una_invalida_no_detienen_a_las_demas(tmp_path):
    historias = ["historias/HU-01-uno.md", "historias/HU-99-envenenada.md", "historias/HU-98-invalida.md",
                 "historias/HU-02-dos.md"]
    valores, _, _ = correr(tmp_path, historias)
    estados = {r["hu"]: r["estado"] for r in valores["resultados"]}
    assert estados == {"HU-01": OK, "HU-02": OK, "HU-99": "bloqueada", "HU-98": FALLA}
    texto = reporte_md(valores["resultados"], valores["costo_usd"], "x")
    assert "flujos.fabrica historias/HU-99" not in texto and "flujos.fabrica historias/HU-98" not in texto


def test_el_motivo_no_esta_en_el_estado_ni_el_checkpoint_ni_el_reporte(tmp_path):
    valores, ensayo, ruta_db = correr(tmp_path, ["historias/HU-99-envenenada.md", "historias/HU-01-uno.md"])
    assert MOTIVO_ENSAYO not in json.dumps(valores, ensure_ascii=False)
    reporte = escribir_reporte(ensayo.salida, valores["resultados"], valores["costo_usd"], "20260101-000000")
    assert MOTIVO_ENSAYO not in reporte.read_text(encoding="utf-8")
    contenido = b"".join(p.read_bytes() for p in ensayo.salida.glob("lote.sqlite*"))
    assert len(contenido) > 0 and MOTIVO_ENSAYO.encode() not in contenido
    # control positivo: el motivo SÍ está donde debe, en registros/
    assert MOTIVO_ENSAYO in (ensayo.registros / "seguridad.jsonl").read_text(encoding="utf-8")


def test_un_error_inesperado_en_una_rama_solo_deja_el_tipo(tmp_path, capsys):
    valores, _, _ = correr(tmp_path, hus(1, 7, 2), explotan={"HU-07"})
    por_hu = {r["hu"]: r for r in valores["resultados"]}
    assert por_hu["HU-01"]["estado"] == OK and por_hu["HU-02"]["estado"] == OK
    assert por_hu["HU-07"] == {"hu": "HU-07", "historia": "historias/HU-07-x.md", "estado": FALLA,
                               "error": "ValueError"}
    assert "ValueError" in capsys.readouterr().err
    assert "no debe salir" not in json.dumps(valores) and "no debe salir" not in capsys.readouterr().err


def test_infraestructura_una_vez_se_reintenta_y_sale_ok(tmp_path):
    valores, ensayo, _ = correr(tmp_path, hus(1, 8), infra={"HU-08": 1})
    assert {r["hu"]: r["estado"] for r in valores["resultados"]} == {"HU-01": OK, "HU-08": OK}
    assert ensayo.llamadas.count("HU-08") == 2          # 2 intentos


def test_infraestructura_agotada_falla_con_el_tipo(tmp_path):
    valores, ensayo, _ = correr(tmp_path, hus(1, 8), infra={"HU-08": 5})
    por_hu = {r["hu"]: r for r in valores["resultados"]}
    assert por_hu["HU-01"]["estado"] == OK
    assert por_hu["HU-08"]["estado"] == FALLA and por_hu["HU-08"]["error"] == "ErrorInfraestructura"
    assert ensayo.llamadas.count("HU-08") == 2          # los mismos 2 intentos que la fábrica, no más


def test_defensas_apagadas_es_sin_filtrar_y_no_es_ok(tmp_path, raiz, monkeypatch, capsys):
    valores, _, _ = correr(tmp_path, hus(1, 2), defensas=False)
    assert {r["estado"] for r in valores["resultados"]} == {SIN_FILTRAR}
    assert "flujos.fabrica historias" not in reporte_md(valores["resultados"], 0.0, "x")
    # y el exit code lo trata como no-ok
    monkeypatch.setattr(lote, "RAIZ", raiz)
    monkeypatch.chdir(raiz)
    monkeypatch.setattr(lote, "validar_historias", lambda r, raiz_=raiz: validar_historias(r, raiz_))
    original = lote.EnsayoLote
    monkeypatch.setattr(lote, "EnsayoLote", lambda salida: original(salida, defensas=False))
    assert main(["historias/HU-01-uno.md", "--ensayo"]) == 1
    capsys.readouterr()


def test_el_costo_del_lote_es_la_suma_de_las_ramas(tmp_path):
    valores, _, _ = correr(tmp_path, hus(1, 2, 3, 4, 5))
    assert valores["costo_usd"] == pytest.approx(0.05)      # 5 ramas × 0.01: el reducer no duplica


# --- registrar_seguridad desde varios hilos -------------------------------------------------------------
def _escribir_en_hilos(registros, hilos=12, por_hilo=4):
    sv = SimpleNamespace(registros=registros)
    grande = "x" * 200_000                  # varias escrituras del SO por evento: se entrelazan si no hay lock

    def trabajo(i):
        for j in range(por_hilo):
            fabrica.registrar_seguridad(sv, f"HU-{i:02d}", [{"evento": "relleno", "detalle": grande, "j": j}])

    ts = [threading.Thread(target=trabajo, args=(i,)) for i in range(hilos)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    lineas = (registros / "seguridad.jsonl").read_text(encoding="utf-8").splitlines()
    invalidas = 0
    for linea in lineas:
        try:
            json.loads(linea)
        except json.JSONDecodeError:
            invalidas += 1
    return len(lineas), invalidas


def test_registrar_seguridad_concurrente_deja_jsonl_valido(tmp_path):
    lineas, invalidas = _escribir_en_hilos(tmp_path / "reg")
    assert (lineas, invalidas) == (12 * 4, 0)


def test_control_negativo_sin_el_lock_el_jsonl_se_puede_corromper(tmp_path, monkeypatch):
    """Sin el lock la prueba de arriba debe poder fallar. Si el SO no entrelaza esta vez, se avisa (skip), no se finge."""
    monkeypatch.setattr(fabrica, "_LOCK_SEGURIDAD", contextlib.nullcontext())
    for intento in range(5):
        lineas, invalidas = _escribir_en_hilos(tmp_path / f"reg{intento}")
        if invalidas or lineas != 12 * 4:
            return                                          # demostrado: sin lock se corrompe
    pytest.skip("no se logró corromper el jsonl sin el lock en este equipo: el control negativo no se demostró")


# --- Entrada y CLI ------------------------------------------------------------------------------------
def test_validar_historias_rechaza_lo_invalido(raiz, monkeypatch):
    monkeypatch.chdir(raiz)
    assert validar_historias([], raiz)[1]
    assert "historias/" in validar_historias(["README.md"], raiz)[1]
    assert "historias/" in validar_historias(["historias/../HU-01-uno.md"], raiz)[1]
    assert "No existe" in validar_historias(["historias/HU-55-nada.md"], raiz)[1]
    assert validar_historias(["historias/backlog.md"], raiz)[1]
    assert "duplicada" in validar_historias(["historias/HU-01-uno.md", "./historias/HU-01-uno.md"], raiz)[1]
    rutas, problema = validar_historias(["historias/HU-02-dos.md", str(raiz / "historias" / "HU-01-uno.md")], raiz)
    assert problema is None and rutas == ["historias/HU-02-dos.md", "historias/HU-01-uno.md"]


def test_la_cli_rechaza_con_mensaje_y_sin_traceback(raiz, monkeypatch, capsys):
    monkeypatch.setattr(lote, "RAIZ", raiz)
    monkeypatch.chdir(raiz)
    monkeypatch.setattr(lote, "validar_historias", lambda r, raiz_=raiz: validar_historias(r, raiz_))
    for argv in ([], ["../fuera.md"], ["historias/HU-01-uno.md", "historias/HU-01-uno.md"]):
        assert main([*argv, "--ensayo"]) == 2
        err = capsys.readouterr().err
        assert err.strip() and "Traceback" not in err


def test_la_cli_ensayo_de_punta_a_punta(raiz, monkeypatch, capsys):
    monkeypatch.setattr(lote, "RAIZ", raiz)
    monkeypatch.chdir(raiz)
    monkeypatch.setattr(lote, "validar_historias", lambda r, raiz_=raiz: validar_historias(r, raiz_))
    codigo = main(["historias/HU-01-uno.md", "historias/HU-99-envenenada.md", "--ensayo"])
    salida = capsys.readouterr().out
    assert codigo == 1                                       # hay una bloqueada
    assert "thread_id: lote-" in salida and "HU-99: bloqueada" in salida and "HU-01: ok" in salida
    assert lote.todas_las_historias(raiz)[0] == "historias/HU-01-uno.md" and "backlog.md" not in " ".join(
        lote.todas_las_historias(raiz))


def test_el_lock_de_fabrica_es_de_modulo():
    assert isinstance(fabrica._LOCK_SEGURIDAD, type(threading.Lock()))
