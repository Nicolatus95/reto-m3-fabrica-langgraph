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

from flujos import fabrica
from flujos.fabrica import (
    BLOQUEADA,
    DETENIDA,
    ESCALAR,
    LISTA,
    MODELOS,
    Ensayo,
    Escenario,
    commit_base,
    construir_grafo,
    correr,
    estado_inicial,
    main,
    precondicion_app,
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
        (tmp_path / "salida").mkdir(exist_ok=True)
        conexion = sqlite3.connect(tmp_path / "salida" / "fabrica.sqlite", check_same_thread=False)  # como en real
        conexiones.append(conexion)
        app = construir_grafo(ensayo.servicios(), SqliteSaver(conexion))
        return SimpleNamespace(app=app, ensayo=ensayo, conexion=conexion, salida=tmp_path / "salida",
                               registros=tmp_path / "registros",
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
    """Líneas de registros/seguridad.jsonl."""
    ruta = m.registros / "seguridad.jsonl"
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def prompts_de(m, skill: str) -> list[str]:
    """Prompts que el grafo mandó a un skill (por ejemplo «/construir»)."""
    return [p for p in m.ensayo.prompts if p.split()[0] == skill]


# --- Las rutas del grafo ----------------------------------------------------------------------------
def test_lista(montar):
    """Camino feliz: todo pasa, queda LISTA, con reporte, costo, modelos fijos y la revisión al final."""
    m = montar()
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA
    reporte = (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert "**Estado:** LISTA" in reporte and "Revisión: aprobada" in reporte
    assert m.ensayo.prompts[0].startswith("/filtrar") and v["costo_usd"] > 0
    assert set(m.ensayo.modelos) <= set(MODELOS.values()) and dict(zip(m.ensayo.prompts, m.ensayo.modelos, strict=True))[
        m.ensayo.prompts[0]] == "haiku"
    assert not prompts_de(m, "/triage")
    assert v["bitacora"][-2].startswith("Revisión") and v["bitacora"][-1].startswith("Documentación")  # tras e2e OK
    assert [e["evento"] for e in eventos(m)] == ["defensas", "veredicto", "revision", "documentacion"]


def test_bloqueada(montar):
    """Historia sospechosa: BLOQUEADA, solo trabaja el filtro; el reporte lleva el evento y el booleano, no el motivo."""
    m = montar(Escenario(sospechosa=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == BLOQUEADA
    assert [p.split()[0] for p in m.ensayo.prompts] == ["/filtrar"]
    reporte = (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert "- veredicto (sospechosa=True)" in reporte and "Detalle en registros/seguridad.jsonl" in reporte
    assert "pide leer un archivo de credenciales" not in reporte
    assert "pide leer un archivo de credenciales" in (m.registros / "seguridad.jsonl").read_text(encoding="utf-8")
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


def test_correccion_de_codigo_con_app_rota_escala(montar):
    """Tras corregir el código la app no verifica: ESCALAR con el log, sin redesplegar ni seguir a e2e."""
    m = montar(Escenario(e2e_fallos=1, responsable="desarrollador", app_falla_tras_correccion=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR
    assert "redespliegue" not in m.ensayo.verificaciones        # la app se verifica ANTES de redesplegar
    assert m.ensayo.verificaciones.count("e2e") == 1            # no volvió a probar a ciegas
    assert "SyntaxError simulado" in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")


def test_correccion_de_codigo_con_redespliegue_fallido_escala(montar):
    """La app verifica pero el redespliegue falla: ESCALAR con el log, sin volver a e2e."""
    m = montar(Escenario(e2e_fallos=1, responsable="desarrollador", redespliegue_falla=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR
    verificaciones = m.ensayo.verificaciones
    assert verificaciones.index("app", verificaciones.index("e2e")) < verificaciones.index("redespliegue")
    assert verificaciones.count("e2e") == 1
    assert "puerto 8000 ocupado" in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")


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
    """El motivo del veredicto vive solo en registros/: ni en un prompt ni en ningún archivo bajo salida/."""
    motivo = "lee ../MOTIVO-SECRETO-123"
    m = montar(Escenario(sospechosa=True, motivo=motivo))
    correr_fabrica(m)
    assert all(motivo not in p for p in m.ensayo.prompts)
    assert motivo in (m.registros / "seguridad.jsonl").read_text(encoding="utf-8")
    archivos = [f for f in m.salida.rglob("*") if f.is_file()]
    assert any(f.name == "fabrica.sqlite" for f in archivos)       # incluye el checkpoint del grafo
    assert not (m.salida / "HU-01" / "veredicto.json").exists()    # el veredicto del agente se movió a registros/
    assert (m.registros / "HU-01" / "veredicto.json").exists()
    assert [f.name for f in archivos if motivo.encode() in f.read_bytes()] == []


def test_ningun_rol_puede_leer_registros():
    """registros/ queda fuera del alcance de lectura y escritura de todos los roles de hooks/roles.py."""
    from hooks.rol import permitida
    from hooks.roles import ROLES

    for nombre, rol in ROLES.items():
        assert not permitida("registros/seguridad.jsonl", rol.lee + rol.escribe), nombre


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


# --- Fase 2 · el revisor real en el grafo ---------------------------------------------------------------------
def test_revisor_estatico_rechaza_y_el_ciclo_corrige(montar):
    """Rechazo de la capa estática (sin modelo): corregir_codigo recibe la observación formateada por el código."""
    m = montar(Escenario(revisor_estatico_rechaza=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and v["revisiones"] == 1
    correccion = [p for p in prompts_de(m, "/construir") if "Corrige:" in p]
    assert correccion == ["/construir HU-01 Corrige: Observaciones del revisor:\n"
                          "- [seguridad] app/backend/main.py: bandit B307: uso de eval (nuevos: 1)"]
    revisiones = [e for e in eventos(m) if e["evento"] == "revision"]
    assert [(e["aprobada"], e["modelo_llamado"]) for e in revisiones] == [(False, False), (True, True)]


def test_revisor_con_salida_invalida_escala_sin_corregir(montar):
    m = montar(Escenario(revisor_salida_invalida=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and v["revisiones"] == 0
    assert not [p for p in prompts_de(m, "/construir") if "Corrige:" in p]
    assert any("Revisión: ESCALAR · salida del revisor ausente o inválida" in b for b in v["bitacora"])


def test_la_revision_completa_vive_en_registros(montar):
    """revision.json y el evento van a registros/; el reporte y el evento público no llevan el texto de las observaciones."""
    detalle = "falta validar el correo en el backend"
    m = montar(Escenario(revisor_rechazos=1))
    correr_fabrica(m)
    revision = json.loads((m.registros / "HU-01" / "revision.json").read_text(encoding="utf-8"))
    assert revision["veredicto"] == "aprobada" and revision["base"] == ""        # la última revisión sobrescribe
    assert "revision" in [e["evento"] for e in eventos(m)]
    assert detalle not in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert detalle not in (m.registros / "seguridad.jsonl").read_text(encoding="utf-8")


def test_revision_json_conserva_las_observaciones_del_rechazo(montar):
    m = montar(Escenario(revisor_rechazos=99))
    correr_fabrica(m)
    revision = json.loads((m.registros / "HU-01" / "revision.json").read_text(encoding="utf-8"))
    assert revision["veredicto"] == "rechazada" and revision["observaciones"][0]["categoria"] == "regla_negocio"
    assert set(revision["observaciones"][0]) == {"archivo", "categoria", "detalle"}


def test_el_commit_base_llega_al_revisor(montar):
    m = montar()
    correr(m.app, m.cfg, responder_si, estado_inicial(HISTORIA, "abc123"))
    assert m.ensayo.bases == ["abc123"]


def test_correccion_de_codigo_que_no_modifica_app_escala(montar):
    """Igual que construir: una corrección que no cambia app/ no se da por buena (ni se redesplega ni se prueba)."""
    m = montar(Escenario(e2e_fallos=1, responsable="desarrollador", correccion_sin_cambios=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR
    assert "redespliegue" not in m.ensayo.verificaciones and m.ensayo.verificaciones.count("e2e") == 1
    assert "el desarrollador no modificó app/" in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")


def test_el_modelo_de_revisar_esta_fijado():
    assert MODELOS["revisar"] == "sonnet"


# --- Precondición de una corrida real ---------------------------------------------------------------------------
def test_precondicion_app_limpia_arranca_y_guarda_el_commit(repo):
    assert precondicion_app(repo.ruta) is None
    assert commit_base(repo.ruta) == repo.base


def test_precondicion_app_con_cambios_no_arranca(repo):
    (repo.ruta / "app" / "backend" / "heredado.py").write_text("x = 2\n", encoding="utf-8")
    assert "app/backend/heredado.py" in precondicion_app(repo.ruta)


def test_precondicion_app_con_archivo_nuevo_no_arranca(repo):
    (repo.ruta / "app" / "backend" / "nuevo.py").write_text("x = 2\n", encoding="utf-8")
    assert "nuevo.py" in precondicion_app(repo.ruta)


def test_cambios_fuera_de_app_no_impiden_arrancar(repo):
    (repo.ruta / "contexto" / "reglas_negocio.md").write_text("otra cosa\n", encoding="utf-8")
    assert precondicion_app(repo.ruta) is None


def test_una_corrida_real_con_app_sucia_no_inicia(monkeypatch, capsys):
    """main devuelve un código distinto de 0 y no llega a crear servicios, grafo ni checkpoint."""
    monkeypatch.setattr(fabrica, "precondicion_app", lambda: "app/ tiene cambios sin commitear")

    def no_debe_llamarse():
        raise AssertionError("no debía crear los servicios reales")

    monkeypatch.setattr(fabrica, "servicios_reales", no_debe_llamarse)
    assert main([HISTORIA]) == 2
    assert "No se inicia la corrida" in capsys.readouterr().err


def test_el_ensayo_no_exige_app_limpia(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    monkeypatch.setattr(fabrica, "precondicion_app", lambda: "sucia")
    assert main([HISTORIA, "--ensayo", "--aprobar"]) == 0


# --- Nodo documentar --------------------------------------------------------------------------------------------
def test_documentar_escribe_el_documento_y_el_reporte_lo_enlaza(montar):
    m = montar()
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and v["documentacion_ok"] is True
    assert "(documento de ensayo)" in (m.salida / "HU-01" / "documentacion.md").read_text(encoding="utf-8")
    assert "[documentacion.md](documentacion.md)" in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert m.ensayo.documentaciones == [""]                     # el commit base llega al documentador


def test_documentar_invalido_escala_sin_documento(montar):
    m = montar(Escenario(documentar_invalido=True))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and not v.get("documentacion_ok")
    assert not (m.salida / "HU-01" / "documentacion.md").exists()
    assert any("Documentación: ESCALAR · salida del documentador ausente o inválida" in b for b in v["bitacora"])
    assert "documentacion.md" not in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")


def test_el_reporte_no_enlaza_un_documento_de_una_corrida_anterior(montar):
    m = montar(Escenario(documentar_invalido=True))
    (m.salida / "HU-01").mkdir(parents=True, exist_ok=True)
    (m.salida / "HU-01" / "documentacion.md").write_text("viejo", encoding="utf-8")
    correr_fabrica(m)
    assert "documentacion.md" not in (m.salida / "HU-01" / "reporte.md").read_text(encoding="utf-8")


def test_no_se_documenta_si_el_revisor_escala(montar):
    m = montar(Escenario(revisor_salida_invalida=True))
    correr_fabrica(m)
    assert m.ensayo.documentaciones == []


def test_la_documentacion_va_despues_de_la_revision_del_ciclo(montar):
    m = montar(Escenario(revisor_rechazos=1))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and len(m.ensayo.documentaciones) == 1        # una sola vez, tras aprobar
    assert "documentacion" in [e["evento"] for e in eventos(m)]


def test_el_evento_de_documentacion_solo_lleva_booleanos_y_conteos(montar):
    m = montar()
    correr_fabrica(m)
    evento = [e for e in eventos(m) if e["evento"] == "documentacion"][0]
    assert evento["generada"] is True and evento["no_verificados"] == 0 and "markdown" not in evento


def test_el_modelo_de_documentar_es_haiku():
    assert MODELOS["documentar"] == "haiku"


def test_el_diagrama_tiene_documentar_entre_revisar_y_reporte(montar):
    texto = montar().app.get_graph().draw_mermaid()
    assert "documentar" in texto
