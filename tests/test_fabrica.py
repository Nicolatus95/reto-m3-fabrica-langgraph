"""Pruebas del grafo de la fábrica, todas en modo ensayo: sin modelo, sin Docker y sin costo.

Cada prueba fuerza una ruta con un Escenario y comprueba el estado final, los prompts que el grafo mandó a los
skills y los archivos que dejó. Los artefactos de los dobles pasan por los validadores de verdad.
"""
import json
import re
import sqlite3
import tempfile
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from flujos import fabrica
from flujos.claude import ErrorInfraestructura
from flujos.fabrica import (
    BLOQUEADA,
    DETENIDA,
    ESCALAR,
    ESPERA_REINTENTO,
    LISTA,
    LLAMAN_AL_MODELO,
    MODELOS,
    MOTIVO_INFRAESTRUCTURA,
    RECURSION_LIMIT,
    Ensayo,
    Escenario,
    calcular_recursion_limit,
    commit_base,
    config_de,
    construir_grafo,
    construir_subgrafo_correccion,
    correr,
    estado_inicial,
    exportar_diagrama,
    exportar_diagrama_correccion,
    historial,
    main,
    politica_de_reintento,
    precondicion_app,
    precondicion_sandbox,
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
        app = construir_grafo(ensayo.servicios(), SqliteSaver(conexion), espera_reintento=0.01)
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
    """El principal trae los nodos clave y el subgrafo «correccion»; el subgrafo trae el triage y las correcciones."""
    m = montar()
    texto = m.app.get_graph().draw_mermaid()
    for nodo in ("filtrar", "correccion", "e2e", "revisar", "documentar", "reporte"):
        assert nodo in texto
    assert "-.->" in texto
    sub = construir_subgrafo_correccion(m.ensayo.servicios(), politica_de_reintento()).get_graph().draw_mermaid()
    for nodo in ("triage", "corregir_codigo", "corregir_pruebas", "corregir_despliegue", "e2e"):
        assert nodo in sub


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


# --- Streaming ----------------------------------------------------------------------------------------------------
def test_el_streaming_imprime_una_linea_por_nodo_con_costo_acumulado(montar):
    m = montar()
    lineas: list[str] = []
    correr(m.app, m.cfg, responder_si, estado_inicial(HISTORIA), emitir=lineas.append)
    patron = re.compile(r"^\d\d:\d\d:\d\d  (\S+)  ·  (.+)  ·  (\d+\.\d{4}) USD$")
    partes = [patron.match(linea) for linea in lineas]
    assert all(partes), lineas
    nodos = [p.group(1) for p in partes]
    assert nodos[0] == "filtrar" and nodos[-1] == "reporte" and "documentar" in nodos and "revisar" in nodos
    costos = [float(p.group(3)) for p in partes]
    assert costos == sorted(costos) and costos[-1] > 0                      # el costo acumulado nunca baja
    assert any("Filtro de seguridad: OK" in linea for linea in lineas)


def test_el_streaming_atiende_las_pausas_humanas(montar):
    m = montar()
    lineas: list[str] = []
    responder = guion("agrega validación de correo", "si")
    v = correr(m.app, m.cfg, responder, estado_inicial(HISTORIA), emitir=lineas.append)
    assert v["estado_final"] == LISTA and len(responder.pausas) == 2
    assert not any("__interrupt__" in linea for linea in lineas)           # la pausa no se imprime como un nodo
    assert [linea.split("  ")[1] for linea in lineas].count("planificar") == 2


def test_reanudar_sigue_imprimiendo_y_parte_del_costo_guardado(montar):
    m1 = montar()
    m1.app.invoke(estado_inicial(HISTORIA), m1.cfg)                        # se corta en la aprobación del plan
    costo_guardado = m1.app.get_state(m1.cfg).values["costo_usd"]
    m1.conexion.close()
    m2 = montar()
    v = reanudar(m2.app, m2.cfg, guion("si"))
    assert v["estado_final"] == LISTA
    assert v["costo_usd"] > costo_guardado > 0


# --- recursion_limit ------------------------------------------------------------------------------------------------
def test_el_limite_de_recursion_sale_de_los_topes():
    from flujos import fabrica
    esperado = (7 + 2 * fabrica.MAX_RECHAZOS + fabrica.MAX_INTENTOS_CONSTRUIR + 3 + 3 * fabrica.MAX_CICLOS
                + 1 + 3 * fabrica.MAX_CICLOS_REVISION + 2)
    assert calcular_recursion_limit(margen=0) == esperado and calcular_recursion_limit() == esperado + 10
    assert RECURSION_LIMIT == 38 and config_de("HU-01-x")["recursion_limit"] == RECURSION_LIMIT


@pytest.mark.parametrize("escenario", [
    Escenario(e2e_fallos=99, responsable="desarrollador"),           # los dos ciclos de corrección y escala
    Escenario(revisor_rechazos=1),                                    # el ciclo de revisión
    Escenario(e2e_fallos=1, responsable="desarrollador", revisor_rechazos=1),
    Escenario(construir_fallos=1),
])
def test_los_caminos_largos_caben_en_el_limite(montar, escenario):
    """El peor camino real termina sin GraphRecursionError y con holgura bajo el límite calculado."""
    m = montar(escenario)
    lineas: list[str] = []
    v = correr(m.app, config_de("HU-01-prueba"), responder_si, estado_inicial(HISTORIA), emitir=lineas.append)
    assert "cortada" not in v and v["estado_final"] in (LISTA, ESCALAR)
    assert len(lineas) <= RECURSION_LIMIT - 5


def test_un_limite_alcanzado_escala_con_mensaje_y_se_puede_reanudar(montar):
    m = montar()
    cfg = {**m.cfg, "recursion_limit": 5}
    v = correr(m.app, cfg, responder_si, estado_inicial(HISTORIA), emitir=lambda _: None)
    assert v["estado_final"] == ESCALAR and "límite de 5 pasos" in v["cortada"]
    assert "--reanudar HU-01-prueba" in v["cortada"] and v["bitacora"][-1].startswith("ESCALAR · se alcanzó")
    v2 = reanudar(m.app, m.cfg, responder_si)                         # el checkpoint no se perdió
    assert v2["estado_final"] == LISTA


def test_main_con_limite_alcanzado_escribe_el_reporte_y_sale_con_1(monkeypatch, tmp_path, capsys):
    from flujos import fabrica
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    monkeypatch.setattr(fabrica, "RECURSION_LIMIT", 4)
    assert main([HISTORIA, "--ensayo", "--aprobar"]) == 1
    captura = capsys.readouterr()
    assert "CORRIDA CORTADA" in captura.err and "Traceback" not in captura.err + captura.out
    reporte = (tmp_path / "salida" / "HU-01" / "reporte.md").read_text(encoding="utf-8")
    assert "ESCALAR A UNA PERSONA" in reporte and "se alcanzó el límite de 4 pasos" in reporte


# --- --historial ---------------------------------------------------------------------------------------------------
def test_historial_lista_los_checkpoints_del_mas_reciente_al_mas_antiguo(montar):
    m = montar()
    correr_fabrica(m)
    lineas = historial(m.app, m.cfg)
    patron = re.compile(r"^paso\s+(-?\d+)  siguiente: (.+?)\s+checkpoint_id: ([0-9a-f-]{36})  \d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
    partes = [patron.match(linea) for linea in lineas]
    assert all(partes), lineas
    pasos = [int(p.group(1)) for p in partes]
    assert pasos == sorted(pasos, reverse=True) and pasos[-1] == -1          # el más antiguo es la entrada (paso -1)
    assert partes[0].group(2) == "(fin)" and len(set(p.group(3) for p in partes)) == len(partes)


def test_historial_no_modifica_la_corrida(montar):
    m = montar()
    correr_fabrica(m)
    antes = (m.app.get_state(m.cfg).values, len(list(m.app.get_state_history(m.cfg))))
    historial(m.app, m.cfg)
    assert (m.app.get_state(m.cfg).values, len(list(m.app.get_state_history(m.cfg)))) == antes


def test_historial_desde_la_cli_en_modo_de_solo_lectura(monkeypatch, tmp_path, capsys, montar):
    from flujos import fabrica
    m = montar()
    correr_fabrica(m)
    m.conexion.close()
    monkeypatch.setattr(fabrica, "RAIZ", tmp_path)                    # salida/fabrica.sqlite de la corrida de prueba
    antes = (tmp_path / "salida" / "fabrica.sqlite").read_bytes()
    assert main(["--historial", "HU-01-prueba"]) == 0
    salida = capsys.readouterr().out
    assert "Historial de HU-01-prueba" in salida and "checkpoint_id:" in salida and "(fin)" in salida
    assert (tmp_path / "salida" / "fabrica.sqlite").read_bytes() == antes


def test_historial_de_un_thread_inexistente_avisa(monkeypatch, tmp_path, capsys, montar):
    from flujos import fabrica
    m = montar()
    correr_fabrica(m)
    m.conexion.close()
    monkeypatch.setattr(fabrica, "RAIZ", tmp_path)
    assert main(["--historial", "HU-77-nada"]) == 2
    assert "No hay checkpoints para el thread HU-77-nada" in capsys.readouterr().err


def test_historial_sin_base_de_datos_avisa(monkeypatch, tmp_path, capsys):
    from flujos import fabrica
    monkeypatch.setattr(fabrica, "RAIZ", tmp_path)
    assert main(["--historial", "HU-01-x"]) == 2
    assert "todavía no hay corridas" in capsys.readouterr().err


# --- RetryPolicy solo para infraestructura ----------------------------------------------------------------------
def test_un_fallo_de_infraestructura_se_reintenta_y_la_corrida_termina(montar):
    m = montar(Escenario(infra_fallos=1))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA
    assert len(prompts_de(m, "/criterios")) == 2                    # el nodo se repitió entero una vez


def test_infraestructura_agotada_escala_sin_traceback(montar):
    m = montar(Escenario(infra_fallos=99))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and MOTIVO_INFRAESTRUCTURA in v["cortada"]
    assert "--reanudar HU-01-prueba" in v["cortada"] and len(prompts_de(m, "/criterios")) == 2
    assert v["bitacora"][-1] == f"ESCALAR · {MOTIVO_INFRAESTRUCTURA}" and not prompts_de(m, "/casos")


def test_la_corrida_cortada_por_infraestructura_se_puede_reanudar(montar):
    m = montar(Escenario(infra_fallos=2))
    assert correr_fabrica(m)["estado_final"] == ESCALAR
    v = reanudar(m.app, m.cfg, responder_si)                        # la infraestructura ya «volvió»
    assert v["estado_final"] == LISTA


def test_un_fallo_de_infraestructura_en_el_revisor_tambien_se_reintenta(montar):
    m = montar(Escenario(infra_revisor_fallos=1))
    v = correr_fabrica(m)
    assert v["estado_final"] == LISTA and len(m.ensayo.bases) == 2


def test_un_artefacto_invalido_no_se_reintenta(montar):
    m = montar(Escenario(sin_artefacto=frozenset({"/criterios"})))
    v = correr_fabrica(m)
    assert v["estado_final"] == ESCALAR and len(prompts_de(m, "/criterios")) == 1 and "cortada" not in v


def test_solo_los_nodos_que_llaman_al_modelo_llevan_la_politica(montar):
    m = montar()
    sub = construir_subgrafo_correccion(m.ensayo.servicios(), politica_de_reintento(0.01))
    en_el_subgrafo = {"triage", "corregir_codigo", "corregir_pruebas", "corregir_despliegue"}
    nodos = [(m.app.nodes[n], n) for n in LLAMAN_AL_MODELO - en_el_subgrafo] + [(sub.nodes[n], n) for n in en_el_subgrafo]
    for nodo, nombre in nodos:
        politica = nodo.retry_policy[0]
        assert politica.max_attempts == 2 and politica.retry_on is ErrorInfraestructura and politica.initial_interval == 0.01, nombre
    for nombre in ("preguntas", "aprobar_plan", "listo", "e2e", "reporte", "correccion"):
        assert not m.app.nodes[nombre].retry_policy
    assert not sub.nodes["e2e"].retry_policy
    assert politica_de_reintento().initial_interval == ESPERA_REINTENTO == 30.0


def test_cli_con_infraestructura_agotada_sale_con_1_y_reporte(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    assert main([HISTORIA, "--ensayo", "--aprobar", "--escenario", "infra_agotada"]) == 1
    captura = capsys.readouterr()
    assert "CORRIDA CORTADA" in captura.err and "Traceback" not in captura.err + captura.out
    assert "sin JSON o tiempo agotado" in (tmp_path / "salida" / "HU-01" / "reporte.md").read_text(encoding="utf-8")


# --- Subgrafo de corrección ---------------------------------------------------------------------------------------
def correr_con_lineas(m, thread: str = "HU-01-prueba"):
    lineas: list[str] = []
    v = correr(m.app, config_de(thread), responder_si, estado_inicial(HISTORIA), emitir=lineas.append)
    return v, lineas


def test_el_subgrafo_no_duplica_costo_bitacora_ni_eventos(montar):
    """Un subgrafo con el mismo Estado fusionaba su salida completa con los reducers: aquí cada cosa cuenta una vez."""
    m = montar(Escenario(e2e_fallos=1, responsable="desarrollador"))
    v, _ = correr_con_lineas(m)
    assert v["estado_final"] == LISTA and v["ciclos"] == 1
    esperado = 0.01 * (len(m.ensayo.prompts) + 2)                          # cada llamada, más revisor y documentador
    assert v["costo_usd"] == pytest.approx(esperado)
    assert len([b for b in v["bitacora"] if b.startswith("Triage")]) == 1
    assert len([b for b in v["bitacora"] if b.startswith("Código corregido")]) == 1
    assert [e["evento"] for e in eventos(m)].count("defensas") == 1


def test_el_streaming_muestra_los_nodos_internos_y_no_cuenta_el_costo_dos_veces(montar):
    m = montar(Escenario(e2e_fallos=1, responsable="desarrollador"))
    v, lineas = correr_con_lineas(m)
    nodos = [linea.split("  ")[1] for linea in lineas]
    assert nodos[nodos.index("e2e"):nodos.index("revisar")] == [
        "e2e", "correccion/triage", "correccion/corregir_codigo", "correccion/e2e", "correccion"]
    assert float(lineas[-1].split("  ·  ")[-1].split()[0]) == pytest.approx(v["costo_usd"])


def test_un_rechazo_del_revisor_entra_al_subgrafo_por_corregir_codigo(montar):
    m = montar(Escenario(revisor_rechazos=1))
    v, lineas = correr_con_lineas(m)
    nodos = [linea.split("  ")[1] for linea in lineas]
    assert v["estado_final"] == LISTA and v["ciclos"] == 0 and v["revisiones"] == 1
    assert "correccion/corregir_codigo" in nodos and "correccion/triage" not in nodos
    assert nodos[nodos.index("correccion"):][:2] == ["correccion", "revisar"] and not prompts_de(m, "/triage")


def test_los_topes_del_ciclo_se_conservan_dentro_del_subgrafo(montar):
    m = montar(Escenario(e2e_fallos=99, responsable="automatizador"))
    v, lineas = correr_con_lineas(m)
    assert v["estado_final"] == ESCALAR and v["ciclos"] == 2 and len(prompts_de(m, "/triage")) == 2
    assert [linea.split("  ")[1] for linea in lineas].count("correccion/e2e") == 2 and not prompts_de(m, "/construir")[1:]


def test_el_fallo_del_triage_termina_el_subgrafo_y_va_a_reporte(montar):
    m = montar(Escenario(e2e_fallos=1, sin_artefacto=frozenset({"/triage"})))
    v, lineas = correr_con_lineas(m)
    assert v["estado_final"] == ESCALAR and any("Triage: ESCALAR" in b for b in v["bitacora"])
    assert [linea.split("  ")[1] for linea in lineas][-2:] == ["correccion", "reporte"] and not prompts_de(m, "/revisar")


def test_una_correccion_cortada_por_infraestructura_se_reanuda_en_el_subgrafo(montar):
    m = montar(Escenario(e2e_fallos=1, responsable="desarrollador", infra_skill="/triage", infra_fallos=2))
    v, _ = correr_con_lineas(m)
    assert v["estado_final"] == ESCALAR and "cortada" in v
    v2 = reanudar(m.app, config_de("HU-01-prueba"), responder_si)
    assert v2["estado_final"] == LISTA and v2["ciclos"] == 1


def test_el_subgrafo_se_exporta_aparte(montar, tmp_path):
    m = montar()
    ruta = exportar_diagrama_correccion(m.ensayo.servicios(), tmp_path / "grafo-correccion.mmd")
    texto = ruta.read_text(encoding="utf-8")
    assert "triage" in texto and "corregir_codigo" in texto and "e2e" in texto
    assert "correccion" in exportar_diagrama(m.app, tmp_path / "grafo.mmd").read_text(encoding="utf-8")


# --- Precondición del sandbox en una corrida real ----------------------------------------------------------------
def test_una_corrida_real_sin_las_imagenes_del_sandbox_no_inicia(monkeypatch, capsys):
    """Falla antes de gastar tokens: sin servicios, sin grafo y con el comando para construir las imágenes."""
    monkeypatch.setattr(fabrica, "precondicion_app", lambda: None)
    monkeypatch.setattr(fabrica, "precondicion_sandbox",
                        lambda: "Faltan las imágenes del sandbox: fabrica-sandbox:1. Constrúyelas con:  python -m verificacion imagen_sandbox")

    def no_debe_llamarse():
        raise AssertionError("no debía crear los servicios reales")

    monkeypatch.setattr(fabrica, "servicios_reales", no_debe_llamarse)
    assert main([HISTORIA]) == 2
    err = capsys.readouterr().err
    assert "No se inicia la corrida" in err and "python -m verificacion imagen_sandbox" in err


def test_con_app_sucia_el_mensaje_es_el_de_app_y_no_se_consulta_docker(monkeypatch, capsys):
    monkeypatch.setattr(fabrica, "precondicion_app", lambda: "app/ tiene cambios sin commitear")
    monkeypatch.setattr(fabrica, "precondicion_sandbox", lambda: pytest.fail("no debía consultar el sandbox"))
    assert main([HISTORIA]) == 2
    assert "cambios sin commitear" in capsys.readouterr().err


def test_el_ensayo_no_exige_docker_ni_imagenes(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    monkeypatch.setattr(fabrica, "precondicion_sandbox", lambda: pytest.fail("el ensayo no usa Docker"))
    assert main([HISTORIA, "--ensayo", "--aprobar"]) == 0


def test_precondicion_sandbox_delega_en_el_ejecutor(monkeypatch):
    monkeypatch.setattr(fabrica.sandbox, "precondicion", lambda: "falta algo")
    assert precondicion_sandbox() == "falta algo"
