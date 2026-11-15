"""Pruebas e2e de HU-02: directorio, búsqueda y filtros (casos CP pares, pytest-playwright)."""
import uuid

import httpx
import pytest
from playwright.sync_api import Page, expect


def token() -> str:
    return uuid.uuid4().hex[:10]


def crear(url_api, nombre, departamento, puesto="Analista", prefijo="emp") -> dict:
    correo = f"{prefijo}.{uuid.uuid4().hex[:12]}@empresa.com"
    r = httpx.post(f"{url_api}/api/empleados", timeout=10, json={
        "nombre": nombre, "correo": correo, "puesto": puesto,
        "departamento": departamento, "fecha_ingreso": "2026-01-10",
    })
    assert r.status_code == 201, r.text
    return r.json()


def abrir_directorio(page: Page, url_web):
    page.goto(url_web)
    expect(page.get_by_test_id("tabla-empleados")).to_be_visible()
    expect(page.get_by_test_id("filtro-departamento")).to_be_visible()


def fila(page: Page, emp: dict):
    return page.get_by_test_id(f"fila-empleado-{emp['id']}")


def test_cp_02_directorio_con_datos(page: Page, url_web, url_api):
    """CP-02: ver el directorio con los datos de cada empleado."""
    t = token()
    ana = crear(url_api, f"Ana Torres {t}", "Tecnología", "Analista", "ana")
    luis = crear(url_api, f"Luis Pérez {t}", "Ventas", "Vendedor", "luis")
    abrir_directorio(page, url_web)
    for emp, nombre, puesto, depto in [
        (ana, f"Ana Torres {t}", "Analista", "Tecnología"),
        (luis, f"Luis Pérez {t}", "Vendedor", "Ventas"),
    ]:
        expect(fila(page, emp)).to_be_visible()
        expect(page.get_by_test_id(f"numero-empleado-{emp['id']}")).to_have_text(emp["numero_empleado"])
        expect(page.get_by_test_id(f"estado-empleado-{emp['id']}")).to_have_text("Activo")
        for texto in (nombre, puesto, depto):
            expect(fila(page, emp)).to_contain_text(texto)


def test_cp_04_buscar_por_nombre(page: Page, url_web, url_api):
    """CP-04: buscar por nombre sin distinguir mayúsculas de minúsculas."""
    t = token()
    ana = crear(url_api, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(url_api, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    abrir_directorio(page, url_web)
    page.get_by_test_id("buscar-empleados").fill(f"ANA TORRES {t}".upper())
    expect(fila(page, ana)).to_be_visible()
    expect(fila(page, luis)).to_have_count(0)


def test_cp_06_buscar_por_correo(page: Page, url_web, url_api):
    """CP-06: buscar por correo sin distinguir mayúsculas de minúsculas."""
    t = token()
    ana = crear(url_api, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(url_api, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    abrir_directorio(page, url_web)
    page.get_by_test_id("buscar-empleados").fill(luis["correo"].swapcase())
    expect(fila(page, luis)).to_be_visible()
    expect(fila(page, ana)).to_have_count(0)


def test_cp_08_filtrar_por_departamento(page: Page, url_web, url_api):
    """CP-08: filtrar por departamento."""
    t = token()
    ana = crear(url_api, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(url_api, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    marta = crear(url_api, f"Marta Gil {t}", "Tecnología", prefijo="marta")
    abrir_directorio(page, url_web)
    expect(page.get_by_test_id("filtro-departamento").locator("option")).not_to_have_count(1)
    page.get_by_test_id("filtro-departamento").select_option("Tecnología")
    expect(fila(page, ana)).to_be_visible()
    expect(fila(page, marta)).to_be_visible()
    expect(fila(page, luis)).to_have_count(0)


def test_cp_10_busqueda_sin_resultados(page: Page, url_web, url_api):
    """CP-10: búsqueda sin resultados muestra un mensaje."""
    crear(url_api, f"Ana Torres {token()}", "Tecnología", prefijo="ana")
    abrir_directorio(page, url_web)
    page.get_by_test_id("buscar-empleados").fill(f"Zacarías-{token()}")
    expect(page.locator("[data-testid^='fila-empleado-']")).to_have_count(0)
    expect(page.get_by_test_id("sin-resultados")).to_be_visible()


def test_cp_12_filtro_departamento_sin_empleados(page: Page, url_web, url_api):
    """CP-12: filtro por departamento sin empleados muestra un mensaje (acotado con un texto único)."""
    t = token()
    ana = crear(url_api, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(url_api, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    abrir_directorio(page, url_web)
    expect(page.get_by_test_id("filtro-departamento").locator("option")).not_to_have_count(1)
    page.get_by_test_id("filtro-departamento").select_option("Finanzas")
    page.get_by_test_id("buscar-empleados").fill(t)
    expect(page.locator("[data-testid^='fila-empleado-']")).to_have_count(0)
    expect(fila(page, ana)).to_have_count(0)
    expect(fila(page, luis)).to_have_count(0)
    expect(page.get_by_test_id("sin-resultados")).to_be_visible()


def test_cp_14_empleado_de_baja_en_directorio(page: Page, url_web, url_api):
    """CP-14: un empleado dado de baja sigue apareciendo en el directorio."""
    marta = crear(url_api, f"Marta Gil {token()}", "Tecnología", prefijo="marta")
    # Ruta de baja asumida: POST /api/empleados/{id}/baja con fecha_baja
    r = httpx.post(f"{url_api}/api/empleados/{marta['id']}/baja", json={"fecha_baja": "2026-03-15"}, timeout=10)
    assert r.status_code == 200, r.text
    abrir_directorio(page, url_web)
    expect(fila(page, marta)).to_be_visible()
    expect(page.get_by_test_id(f"numero-empleado-{marta['id']}")).to_have_text(marta["numero_empleado"])
    expect(page.get_by_test_id(f"estado-empleado-{marta['id']}")).to_have_text("Baja")
