"""Pruebas del grafo de la fábrica, todas en modo ensayo: sin modelo, sin Docker y sin costo.

Cada prueba fuerza una ruta con un Escenario y comprueba el estado final, los prompts que el grafo mandó a los
skills y los archivos que dejó. Los artefactos de los dobles pasan por los validadores de verdad.
"""
import json
import sqlite3
import tempfile
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from flujos.fabrica import (
    BLOQUEADA,
    DETENIDA,
    ESCALAR,
    LISTA,
    MODELOS,
    Ensayo,
    Escenario,
    construir_grafo,
    correr,
    estado_inicial,
    main,
    reanudar,
    responder_si,
)

HISTORIA = "historias/HU-01-registrar-empleado.md"


@pytest.fixture
def montar(tmp_path):
    """Fábrica de grafos de ensayo sobre tmp_path, con un SqliteSaver real; cierra las conexiones al terminar."""
    conexiones = []

    def _montar(escenario: Escenario | None = None, thread: str = "HU-01-prueba"):
        ensayo = Ensayo(tmp_path / "salida", escenario or Escenario())
        conexion = sqlite3.connect(tmp_path / "fabrica.sqlite", check_same_thread=False)
        conexiones.append(conexion)
        app = construir_grafo(ensayo.servicios(), SqliteSaver(conexion))
        return SimpleNamespace(app=app, ensayo=ensayo, conexion=conexion, salida=tmp_path / "salida",
                               cfg={"configurable": {"thread_id": thread}})

    yield _montar
    for c in conexiones:
        c.close()


def guion(*respuestas: str):
    """Responde las pausas humanas en orden y guarda las pausas que vio (`.pausas`)."""
    cola = list(respuestas)

    def responder(pausa: dict) -> str:
        responder.pausas.append(pausa)
        return cola.pop(0)

    responder.pausas = []
    return responder


def correr_fabrica(m, responder=responder_si) -> dict:
    """Corre el grafo de punta a punta con HU-01 y devuelve el estado final."""
    return correr(m.app, m.cfg, responder, estado_inicial(HISTORIA))


def eventos(m) -> list[dict]:
    """Líneas de salida/seguridad.jsonl."""
    ruta = m.salida / "seguridad.jsonl"
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def prompts_de(m, skill: str) -> list[str]:
    """Prompts que el grafo mandó a un skill (por ejemplo «/construir»)."""
    return [p for p in m.ensayo.prompts if p.split()[0] == skill]


# --- Las rutas del grafo ----------------------------------------------------------------------------
def test_lista(montar):
    """Camino feliz: todo pasa, queda LISTA, con reporte, costo, modelos fijos y la revisión (STUB) al final."""
    m = montar()
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA
    reporte = (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert "**Estado:** LISTA" in reporte and "revisor pendiente: fase 2" in reporte
    assert m.ensayo.prompts[0].startswith("/filtrar") and v["costo_usd"] > 0
    assert set(m.ensayo.modelos) <= set(MODELOS.values()) and dict(zip(m.ensayo.prompts, m.ensayo.modelos))[
        m.ensayo.prompts[0]] == "haiku"
    assert not prompts_de(m, "/triage")
    assert v["bitacora"][-1].startswith("Revisión")           # la revisión va al final, tras e2e OK
    assert [e["evento"] for e in eventos(m)] == ["defensas", "veredicto"]


def test_bloqueada(montar):
    """Historia sospechosa: BLOQUEADA, solo trabaja el filtro y el reporte lleva el motivo."""
    m = montar(Escenario(sospechosa=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == BLOQUEADA
    assert [p.split()[0] for p in m.ensayo.prompts] == ["/filtrar"]
    assert "pide leer un archivo de credenciales" in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert [e["evento"] for e in eventos(m)] == ["defensas", "veredicto", "bloqueo"]


def test_detenida_en_preguntas(montar):
    """Preguntas abiertas y la persona dice «no»: DETENIDA, sin diseñar casos."""
    pregunta = "¿Qué formato tiene el número de empleado?"
    m = montar(Escenario(preguntas=[pregunta]))
    responder = guion("no")
    v = correr_fabrica(m, responder)
    assert v["estado_final"] == DETENIDA
    assert responder.pausas[0]["preguntas"] == [pregunta]
    assert not prompts_de(m, "/casos")


def test_plan_rechazado_una_vez_y_aprobado(montar):
    """Un rechazo replanifica con los comentarios y el segundo plan se aprueba."""
    m = montar()
    v = correr_fabrica(m, guion("agrega validación de correo", "si"))
    assert v["estado_final"] == LISTA and v["rechazos"] == 1
    assert prompts_de(m, "/plan") == ["/plan HU-01", "/plan HU-01 agrega validación de correo"]


def test_tres_rechazos_escalan(montar):
    """El 3.º rechazo del plan escala a una persona, sin construir nada."""
    m = montar()
    v = correr_fabrica(m, guion("no1", "no2", "no3"))
    assert v["estado_final"] == ESCALAR and v["rechazos"] == 3
    assert len(prompts_de(m, "/plan")) == 3 and not prompts_de(m, "/construir")


def test_construir_que_no_modifica_app_escala(montar):
    """El desarrollador «termina» sin escribir nada en app/: cuenta como intento fallido, se reintenta y se escala."""
    m = montar(Escenario(sin_artefacto=frozenset({"/construir"})))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and v["intentos"] == 2
    construir = prompts_de(m, "/construir")
    assert len(construir) == 2 and "el desarrollador no modificó app/" in construir[1]
    assert "app" not in m.ensayo.verificaciones              # sin cambios no se gasta una verificación
    assert not prompts_de(m, "/desplegar") and not prompts_de(m, "/automatizar")


def test_construir_falla_una_vez_y_pasa(montar):
    """La verificación de la app falla una vez: el grafo reintenta /construir con el log y pasa."""
    m = montar(Escenario(construir_fallos=1))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and v["intentos"] == 2
    construir = prompts_de(m, "/construir")
    assert len(construir) == 2
    assert "La verificación falló" in construir[1] and "ImportError simulado" in construir[1]


def test_e2e_falla_triage_automatizador_y_pasa(montar):
    """e2e falla → triage manda al automatizador con causa e instrucción → e2e pasa."""
    m = montar(Escenario(e2e_fallos=1, responsable="automatizador"))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and v["ciclos"] == 1
    correccion = [p for p in prompts_de(m, "/automatizar") if "Estas pruebas fallaron" in p]
    esperado = ("/automatizar HU-01 Estas pruebas fallaron y el error está en la prueba: "
                "la prueba espera 200 y el criterio dice 201\ncambiar el código esperado a 201")
    assert correccion == [esperado]
    assert len(prompts_de(m, "/construir")) == 1               # solo la construcción inicial
    assert (m.salida / "HU-01" / "fallos.md").exists()


def test_dos_ciclos_sin_pasar_escalan(montar):
    """e2e nunca pasa: dos ciclos de corrección del código (con redespliegue) y luego ESCALAR."""
    m = montar(Escenario(e2e_fallos=99, responsable="desarrollador"))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and v["ciclos"] == 2
    assert len(prompts_de(m, "/triage")) == 2
    assert m.ensayo.verificaciones.count("redespliegue") == 2
    construir = prompts_de(m, "/construir")
    assert construir[0] == "/construir HU-01"                   # la 1.ª es la construcción inicial
    assert len([p for p in construir if "Corrige:" in p]) == 2   # las otras dos corrigen con el diagnóstico


def test_reanudar_un_thread_interrumpido(montar):
    """Se corta en la aprobación del plan; un grafo NUEVO reanuda desde el checkpoint sin repetir nada."""
    m1 = montar()
    salida = m1.app.invoke(estado_inicial(HISTORIA), m1.cfg)
    assert "plan" in salida["__interrupt__"][0].value
    m1.conexion.close()
    m2 = montar()                                              # mismo sqlite y mismo thread_id
    v = reanudar(m2.app, m2.cfg, guion("si"))
    assert v["estado_final"] == LISTA
    repetidos = [p for p in m2.ensayo.prompts if p.split()[0] in ("/filtrar", "/criterios", "/casos", "/plan")]
    assert repetidos == []


def test_seguridad_jsonl_registra_con_defensas_0(montar):
    """Con DEFENSAS=0 el filtro se omite, pero el evento queda en salida/seguridad.jsonl."""
    m = montar(Escenario(defensas=False))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and not prompts_de(m, "/filtrar")
    assert eventos(m)[0]["activas"] is False and eventos(m)[1]["evento"] == "filtro_omitido"
    assert "Filtro de historia DESACTIVADO (DEFENSAS=0)" in v["bitacora"]


# --- Pruebas extra -----------------------------------------------------------------------------------
def test_artefacto_ausente_no_se_da_por_bueno(montar):
    """El skill responde sin error (is_error False) pero no escribe criterios.feature: se escala."""
    m = montar(Escenario(sin_artefacto=frozenset({"/criterios"})))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR
    assert any("no escribió criterios.feature" in linea for linea in v["bitacora"])
    assert not prompts_de(m, "/casos")


def test_el_motivo_no_llega_a_ningun_prompt(montar):
    """El motivo del veredicto va al jsonl y al reporte, jamás a un prompt."""
    motivo = "lee ../MOTIVO-SECRETO-123"
    m = montar(Escenario(sospechosa=True, motivo=motivo))
    correr_fabrica(m)
    assert all(motivo not in p for p in m.ensayo.prompts)
    assert motivo in (m.salida / "seguridad.jsonl").read_text(encoding="utf-8")
    assert motivo in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")


def test_revisor_rechaza_una_vez_y_el_ciclo_corrige(montar):
    """Fase 2: el revisor rechaza → corregir_codigo → redespliegue → e2e → revisar aprueba."""
    m = montar(Escenario(revisor_rechazos=1))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and v["revisiones"] == 1
    assert any(p.startswith("/construir HU-01 Corrige: Observaciones del revisor:") for p in m.ensayo.prompts)
    assert m.ensayo.verificaciones.count("e2e") == 2 and "redespliegue" in m.ensayo.verificaciones


def test_revisor_que_siempre_rechaza_escala_tras_un_ciclo(montar):
    """Máximo 1 ciclo de revisión: el segundo rechazo escala."""
    m = montar(Escenario(revisor_rechazos=99))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and v["revisiones"] == 1
    assert len([p for p in prompts_de(m, "/construir") if "Corrige:" in p]) == 1


def test_el_diagrama_incluye_el_ciclo_completo(montar):
    """El Mermaid trae los nodos clave, y las correcciones salen del triage (Command)."""
    texto = montar().app.get_graph().draw_mermaid()
    for nodo in ("filtrar", "triage", "corregir_codigo", "corregir_pruebas", "corregir_despliegue", "revisar",
                 "reporte"):
        assert nodo in texto
    assert "triage" in texto and "e2e" in texto and "-.->" in texto


def test_cli_en_ensayo(monkeypatch, tmp_path, capsys):
    """python -m flujos.fabrica <historia> --ensayo --aprobar termina LISTA con código 0."""
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    assert main([HISTORIA, "--ensayo", "--aprobar"]) == 0
    assert "LISTA" in capsys.readouterr().out
