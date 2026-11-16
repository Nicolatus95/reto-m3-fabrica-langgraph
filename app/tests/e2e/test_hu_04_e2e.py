"""Pruebas e2e de HU-04: jefe directo de un empleado (casos CP pares, pytest-playwright)."""
import uuid

import httpx
from playwright.sync_api import Page, expect


def crear(url_api, nombre="Persona") -> dict:
    nombre_unico = f"{nombre} {uuid.uuid4().hex[:8]}"
    r = httpx.post(f"{url_api}/api/empleados", timeout=10, json={
        "nombre": nombre_unico,
        "correo": f"emp.{uuid.uuid4().hex[:12]}@empresa.com",
        "puesto": "Analista", "departamento": "Ventas", "fecha_ingreso": "2024-03-01",
    })
    assert r.status_code == 201, r.text
    return r.json()


def asignar_api(url_api, emp, jefe):
    r = httpx.put(f"{url_api}/api/empleados/{emp['id']}", json={"jefe_id": jefe["id"]}, timeout=10)
    assert r.status_code == 200, r.text


def abrir_directorio(page: Page, url_web):
    page.goto(url_web)
    expect(page.get_by_test_id("tabla-empleados")).to_be_visible()


def fila(page: Page, emp: dict):
    return page.get_by_test_id(f"fila-empleado-{emp['id']}")


def abrir_edicion(page: Page, emp: dict):
    page.get_by_test_id(f"editar-empleado-{emp['id']}").click()
    expect(page.get_by_test_id("empleado-jefe")).to_be_visible()


def test_cp_02_asignar_jefe(page: Page, url_web, url_api):
    """CP-02: asignar como jefe a un empleado activo desde el formulario."""
    ana, luis = crear(url_api, "Ana"), crear(url_api, "Luis")
    abrir_directorio(page, url_web)
    abrir_edicion(page, luis)
    page.get_by_test_id("empleado-jefe").select_option(label=ana["nombre"])
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id("mensaje-exito")).to_be_visible()
    expect(page.get_by_test_id(f"jefe-empleado-{luis['id']}")).to_have_text(ana["nombre"])


def test_cp_04_ver_nombre_del_jefe(page: Page, url_web, url_api):
    """CP-04: la fila del subordinado muestra el nombre de su jefe."""
    ana, luis = crear(url_api, "Ana"), crear(url_api, "Luis")
    asignar_api(url_api, luis, ana)
    abrir_directorio(page, url_web)
    expect(fila(page, luis)).to_be_visible()
    expect(page.get_by_test_id(f"jefe-empleado-{luis['id']}")).to_have_text(ana["nombre"])


def test_cp_06_quitar_jefe(page: Page, url_web, url_api):
    """CP-06: quitar el jefe de un empleado desde el formulario."""
    ana, luis = crear(url_api, "Ana"), crear(url_api, "Luis")
    asignar_api(url_api, luis, ana)
    abrir_directorio(page, url_web)
    abrir_edicion(page, luis)
    page.get_by_test_id("empleado-jefe").select_option(value="")
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id("mensaje-exito")).to_be_visible()
    expect(page.get_by_test_id(f"jefe-empleado-{luis['id']}")).to_have_text("")
    expect(fila(page, luis)).not_to_contain_text(ana["nombre"])


def test_cp_08_no_ofrece_propio_jefe(page: Page, url_web, url_api):
    """CP-08: la UI no permite elegir al propio empleado como jefe (el 422 se cubre en CP-07)."""
    ana = crear(url_api, "Ana")
    abrir_directorio(page, url_web)
    abrir_edicion(page, ana)
    selector = page.get_by_test_id("empleado-jefe")
    expect(selector.locator("option", has_text=ana["nombre"])).to_have_count(0)
    page.get_by_test_id("empleado-guardar").click()
    expect(page.get_by_test_id(f"jefe-empleado-{ana['id']}")).to_have_text("")


def test_cp_14_baja_de_jefe_libera_subordinados(page: Page, url_web, url_api):
    """CP-14: al dar de baja a un jefe las filas de sus subordinados no muestran jefe."""
    ana, luis, eva = crear(url_api, "Ana"), crear(url_api, "Luis"), crear(url_api, "Eva")
    asignar_api(url_api, luis, ana)
    asignar_api(url_api, eva, ana)
    abrir_directorio(page, url_web)
    page.get_by_test_id(f"baja-empleado-{ana['id']}").click()
    page.get_by_test_id("empleado-fecha-baja").fill("2026-11-15")
    page.get_by_test_id("confirmar-baja").click()
    expect(page.get_by_test_id(f"estado-empleado-{ana['id']}")).to_have_text("Baja")
    expect(page.get_by_test_id(f"jefe-empleado-{luis['id']}")).to_have_text("")
    expect(page.get_by_test_id(f"jefe-empleado-{eva['id']}")).to_have_text("")
