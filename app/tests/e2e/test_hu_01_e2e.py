"""Pruebas e2e de HU-01: registro de empleados (casos CP pares, pytest-playwright)."""
import re
import uuid

import httpx
import pytest
from playwright.sync_api import Page, expect


def correo_unico(prefijo="emp") -> str:
    return f"{prefijo}.{uuid.uuid4().hex[:12]}@empresa.com"


def datos_validos(**cambios) -> dict:
    datos = {
        "nombre": "Ana Torres",
        "correo": correo_unico("ana"),
        "puesto": "Analista",
        "departamento": "Finanzas",
        "fecha_ingreso": "2024-03-15",
    }
    datos.update(cambios)
    return datos


def esperar_catalogo(page: Page):
    expect(page.get_by_test_id("empleado-guardar")).to_be_visible()
    expect(page.get_by_test_id("empleado-departamento").locator("option")).not_to_have_count(1)


@pytest.fixture
def abrir(page: Page, url_web):
    page.goto(url_web)
    esperar_catalogo(page)
    return page


def llenar(page: Page, datos: dict, forzar_departamento=False):
    page.get_by_test_id("empleado-nombre").fill(datos["nombre"])
    page.get_by_test_id("empleado-correo").fill(datos["correo"])
    page.get_by_test_id("empleado-puesto").fill(datos["puesto"])
    selector = page.get_by_test_id("empleado-departamento")
    if forzar_departamento:
        selector.evaluate(
            "(el, v) => { const o = document.createElement('option'); o.value = v; o.text = v; el.appendChild(o); }",
            datos["departamento"],
        )
    selector.select_option(datos["departamento"])
    if datos["fecha_ingreso"]:
        page.get_by_test_id("empleado-fecha-ingreso").fill(datos["fecha_ingreso"])


def guardar(page: Page):
    page.get_by_test_id("empleado-guardar").click()


def filas(page: Page) -> int:
    return page.locator("[data-testid^='fila-empleado-']").count()


def total_api(url_api) -> int:
    return len(httpx.get(f"{url_api}/api/empleados", timeout=10).json())


def buscar_por_correo(url_api, correo: str) -> dict:
    r = httpx.get(f"{url_api}/api/empleados", timeout=10)
    assert r.status_code == 200, r.text
    for emp in r.json():
        if emp["correo"] == correo.lower():
            return emp
    raise AssertionError(f"No se encontró {correo} en la API")


def test_cp_02_registro_exitoso(abrir, url_api):
    """CP-02: registro exitoso con número de empleado asignado por el sistema."""
    page = abrir
    datos = datos_validos()
    llenar(page, datos)
    guardar(page)
    exito = page.get_by_test_id("mensaje-exito")
    expect(exito).to_contain_text(re.compile(r"EMP-\d{4}"))
    emp = buscar_por_correo(url_api, datos["correo"])
    expect(exito).to_contain_text(emp["numero_empleado"])
    expect(page.get_by_test_id(f"numero-empleado-{emp['id']}")).to_have_text(emp["numero_empleado"])
    expect(page.get_by_test_id(f"estado-empleado-{emp['id']}")).to_have_text("Activo")


def test_cp_04_numero_consecutivo(abrir, url_api):
    """CP-04: el número de empleado es consecutivo."""
    page = abrir
    previo = httpx.post(f"{url_api}/api/empleados", json=datos_validos(), timeout=10)
    assert previo.status_code == 201, previo.text
    siguiente = f"EMP-{int(previo.json()['numero_empleado'].split('-')[1]) + 1:04d}"
    page.reload()
    esperar_catalogo(page)
    datos = datos_validos(nombre="Luis Pérez", correo=correo_unico("luis"), puesto="Ejecutivo de ventas",
                          departamento="Ventas", fecha_ingreso="2024-05-02")
    llenar(page, datos)
    guardar(page)
    expect(page.get_by_test_id("mensaje-exito")).to_contain_text(siguiente)
    emp = buscar_por_correo(url_api, datos["correo"])
    expect(page.get_by_test_id(f"numero-empleado-{emp['id']}")).to_have_text(siguiente)


def test_cp_06_correo_en_minusculas(abrir, url_api):
    """CP-06: el correo se guarda en minúsculas."""
    page = abrir
    base = uuid.uuid4().hex[:12]
    datos = datos_validos(nombre="Marta Ruiz", correo=f"Marta.{base}@Empresa.com", puesto="Desarrolladora",
                          departamento="Tecnología", fecha_ingreso="2024-01-10")
    llenar(page, datos)
    guardar(page)
    expect(page.get_by_test_id("mensaje-exito")).to_be_visible()
    esperado = f"marta.{base}@empresa.com"
    fila = page.get_by_test_id("tabla-empleados").locator("tr", has_text=esperado)
    expect(fila).to_have_count(1)
    expect(fila).to_contain_text(esperado)
    assert buscar_por_correo(url_api, esperado)["correo"] == esperado


def test_cp_08_correo_duplicado(abrir, url_api):
    """CP-08: correo duplicado sin importar mayúsculas."""
    page = abrir
    original = datos_validos()
    assert httpx.post(f"{url_api}/api/empleados", json=original, timeout=10).status_code == 201
    page.reload()
    esperar_catalogo(page)
    expect(page.get_by_test_id("tabla-empleados")).to_be_visible()
    antes = total_api(url_api)
    llenar(page, datos_validos(nombre="Ana Torres Díaz", correo=original["correo"].upper(), puesto="Contadora",
                               fecha_ingreso="2024-06-01"))
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_have_text("El correo ya está registrado")
    assert total_api(url_api) == antes


def test_cp_10_correo_no_corporativo(abrir, url_api):
    """CP-10: correo que no es del dominio corporativo."""
    page = abrir
    antes = total_api(url_api)
    llenar(page, datos_validos(correo=f"ana.{uuid.uuid4().hex[:10]}@gmail.com"))
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_have_text("Usa el correo corporativo @empresa.com")
    assert total_api(url_api) == antes


def test_cp_12_fecha_futura(abrir, url_api):
    """CP-12: fecha de ingreso futura."""
    page = abrir
    antes = total_api(url_api)
    llenar(page, datos_validos(nombre="Pedro Gil", correo=correo_unico("pedro"), puesto="Operador",
                               departamento="Operaciones", fecha_ingreso="2099-01-01"))
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_have_text("La fecha de ingreso no puede ser futura")
    assert total_api(url_api) == antes


def test_cp_14_nombre_corto(abrir, url_api):
    """CP-14: nombre demasiado corto."""
    page = abrir
    antes = total_api(url_api)
    llenar(page, datos_validos(nombre="A", correo=correo_unico("ab"), departamento="Tecnología"))
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("nombre")
    assert total_api(url_api) == antes


def test_cp_16_puesto_vacio(abrir, url_api):
    """CP-16: puesto vacío."""
    page = abrir
    antes = total_api(url_api)
    llenar(page, datos_validos(nombre="Sofía Mena", correo=correo_unico("sofia"), puesto="",
                               departamento="Recursos Humanos"))
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("puesto")
    assert total_api(url_api) == antes


def test_cp_18_departamento_fuera_catalogo(abrir, url_api):
    """CP-18: departamento fuera de la lista permitida (se fuerza la opción Marketing en el select)."""
    page = abrir
    antes = total_api(url_api)
    llenar(page, datos_validos(nombre="Raúl Vega", correo=correo_unico("raul"), departamento="Marketing"),
           forzar_departamento=True)
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("departamento")
    assert total_api(url_api) == antes


def test_cp_20_falta_fecha_ingreso(abrir, url_api):
    """CP-20: fecha de ingreso ausente."""
    page = abrir
    antes = total_api(url_api)
    llenar(page, datos_validos(nombre="Eva Lara", correo=correo_unico("eva"), departamento="Ventas",
                               fecha_ingreso=""))
    guardar(page)
    expect(page.get_by_test_id("mensaje-error")).to_contain_text("fecha_ingreso")
    assert total_api(url_api) == antes
