"""Pruebas e2e de HU-03: edición y baja de empleados (casos CP pares, pytest-playwright)."""
import uuid

import httpx
from playwright.sync_api import Page, expect

MENSAJE_BAJA = "No se puede editar a un empleado dado de baja"


def crear(url_api, puesto="Analista", departamento="Ventas", fecha_ingreso="2024-03-01") -> dict:
    correo = f"emp.{uuid.uuid4().hex[:12]}@empresa.com"
    r = httpx.post(f"{url_api}/api/empleados", timeout=10, json={
        "nombre": f"Ana López {uuid.uuid4().hex[:8]}", "correo": correo, "puesto": puesto,
        "departamento": departamento, "fecha_ingreso": fecha_ingreso,
    })
    assert r.status_code == 201, r.text
    return r.json()


def dar_de_baja_api(url_api, emp, fecha="2026-10-15"):
    r = httpx.post(f"{url_api}/api/empleados/{emp['id']}/baja", json={"fecha_baja": fecha}, timeout=10)
    assert r.status_code == 200, r.text


def abrir_directorio(page: Page, url_web):
    page.goto(url_web)
    expect(page.get_by_test_id("tabla-empleados")).to_be_visible()


def fila(page: Page, emp: dict):
    return page.get_by_test_id(f"fila-empleado-{emp['id']}")


def abrir_edicion(page: Page, emp: dict):
    page.get_by_test_id(f"editar-empleado-{emp['id']}").click()
    expect(page.get_by_test_id("empleado-puesto")).to_be_visible()


def test_cp_02_editar_puesto_y_departamento(page: Page, url_web, url_api):
    """CP-02: editar puesto y departamento de un empleado activo."""
    emp = crear(url_api)
    abrir_directorio(page, url_web)
    abrir_edicion(page, emp)
    page.get_by_test_id("empleado-puesto").fill("Líder de Finanzas")
    page.get_by_test_id("empleado-departamento").select_option("Finanzas")
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id("mensaje-exito")).to_be_visible()
    expect(fila(page, emp)).to_contain_text("Líder de Finanzas")
    expect(fila(page, emp)).to_contain_text("Finanzas")
    expect(page.get_by_test_id(f"numero-empleado-{emp['id']}")).to_have_text(emp["numero_empleado"])
    expect(page.get_by_test_id(f"estado-empleado-{emp['id']}")).to_have_text("Activo")


def test_cp_04_rechazar_departamento_invalido(page: Page, url_web, url_api):
    """CP-04: rechazar un departamento fuera de la lista (la UI no ofrece 'Marketing'; el 422 se cubre en CP-03)."""
    emp = crear(url_api, departamento="Ventas")
    abrir_directorio(page, url_web)
    abrir_edicion(page, emp)
    selector = page.get_by_test_id("empleado-departamento")
    expect(selector.locator("option[value='Marketing']")).to_have_count(0)
    expect(selector.locator("option")).not_to_have_count(0)
    # La fila sigue mostrando Ventas porque no se pudo elegir un departamento inválido
    expect(fila(page, emp)).to_contain_text("Ventas")


def test_cp_06_rechazar_puesto_de_un_caracter(page: Page, url_web, url_api):
    """CP-06: rechazar un puesto de un solo carácter."""
    emp = crear(url_api)
    abrir_directorio(page, url_web)
    abrir_edicion(page, emp)
    page.get_by_test_id("empleado-puesto").fill("A")
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("puesto")
    expect(fila(page, emp)).to_contain_text("Analista")


def test_cp_08_rechazar_puesto_de_mas_de_60(page: Page, url_web, url_api):
    """CP-08: rechazar un puesto de más de 60 caracteres."""
    emp = crear(url_api)
    abrir_directorio(page, url_web)
    abrir_edicion(page, emp)
    page.get_by_test_id("empleado-puesto").fill("A" * 61)
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("puesto")
    expect(fila(page, emp)).to_contain_text("Analista")


def test_cp_10_dar_de_baja_empleado_activo(page: Page, url_web, url_api):
    """CP-10: dar de baja a un empleado activo."""
    emp = crear(url_api)
    abrir_directorio(page, url_web)
    page.get_by_test_id(f"baja-empleado-{emp['id']}").click()
    page.get_by_test_id("empleado-fecha-baja").fill("2026-10-15")
    page.get_by_test_id("confirmar-baja").click()
    expect(page.get_by_test_id("mensaje-exito")).to_be_visible()
    tabla = page.get_by_test_id("tabla-empleados")
    expect(tabla.get_by_test_id(f"estado-empleado-{emp['id']}")).to_have_text("Baja")
    expect(tabla.get_by_test_id(f"fila-empleado-{emp['id']}")).to_be_visible()


def test_cp_12_rechazar_baja_anterior_al_ingreso(page: Page, url_web, url_api):
    """CP-12: rechazar una fecha de baja anterior a la fecha de ingreso."""
    emp = crear(url_api, fecha_ingreso="2024-03-01")
    abrir_directorio(page, url_web)
    page.get_by_test_id(f"baja-empleado-{emp['id']}").click()
    page.get_by_test_id("empleado-fecha-baja").fill("2024-02-28")
    page.get_by_test_id("confirmar-baja").click()
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("fecha_baja")
    expect(page.get_by_test_id(f"estado-empleado-{emp['id']}")).to_have_text("Activo")


def test_cp_14_no_editar_empleado_de_baja(page: Page, url_web, url_api):
    """CP-14: no se puede editar a un empleado dado de baja."""
    emp = crear(url_api)
    dar_de_baja_api(url_api, emp)
    abrir_directorio(page, url_web)
    abrir_edicion(page, emp)
    page.get_by_test_id("empleado-puesto").fill("Gerente")
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id("mensaje-error")).to_contain_text(MENSAJE_BAJA)
    expect(fila(page, emp)).to_contain_text("Analista")
