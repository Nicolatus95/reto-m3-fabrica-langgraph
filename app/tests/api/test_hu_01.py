"""Pruebas de API de HU-01: registro de empleados (casos CP impares)."""
import re
import uuid
from datetime import date, timedelta

import httpx
import pytest


@pytest.fixture
def cliente(url_api):
    with httpx.Client(base_url=url_api, timeout=10) as c:
        yield c


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


def numero(emp: dict) -> int:
    return int(emp["numero_empleado"].split("-")[1])


def total(cliente) -> int:
    return len(cliente.get("/api/empleados").json())


def afirma_422_campo(r, campo):
    assert r.status_code == 422, r.text
    assert campo in r.text


def test_cp_01_registro_exitoso(cliente):
    """CP-01: registro exitoso con número de empleado asignado por el sistema."""
    datos = datos_validos()
    r = cliente.post("/api/empleados", json=datos)
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert re.fullmatch(r"EMP-\d{4}", cuerpo["numero_empleado"])
    assert cuerpo["estado"] == "activo"
    assert cuerpo["creado_en"]
    lista = cliente.get("/api/empleados").json()
    guardado = [e for e in lista if e["correo"] == datos["correo"]]
    assert len(guardado) == 1
    assert guardado[0]["numero_empleado"] == cuerpo["numero_empleado"]


def test_cp_03_numero_consecutivo(cliente):
    """CP-03: el número de empleado es consecutivo."""
    primero = cliente.post("/api/empleados", json=datos_validos())
    assert primero.status_code == 201, primero.text
    segundo = cliente.post(
        "/api/empleados",
        json=datos_validos(nombre="Luis Pérez", correo=correo_unico("luis"), puesto="Ejecutivo de ventas",
                           departamento="Ventas", fecha_ingreso="2024-05-02"),
    )
    assert segundo.status_code == 201, segundo.text
    assert numero(segundo.json()) == numero(primero.json()) + 1


def test_cp_05_correo_en_minusculas(cliente):
    """CP-05: el correo se guarda en minúsculas."""
    base = uuid.uuid4().hex[:12]
    r = cliente.post(
        "/api/empleados",
        json=datos_validos(nombre="Marta Ruiz", correo=f"Marta.{base}@Empresa.com", puesto="Desarrolladora",
                           departamento="Tecnología", fecha_ingreso="2024-01-10"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["correo"] == f"marta.{base}@empresa.com"


def test_cp_07_correo_duplicado(cliente):
    """CP-07: correo duplicado sin importar mayúsculas."""
    original = datos_validos()
    assert cliente.post("/api/empleados", json=original).status_code == 201
    antes = total(cliente)
    r = cliente.post(
        "/api/empleados",
        json=datos_validos(nombre="Ana Torres Díaz", correo=original["correo"].upper(), puesto="Contadora",
                           fecha_ingreso="2024-06-01"),
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "El correo ya está registrado"
    assert total(cliente) == antes


def test_cp_09_correo_no_corporativo(cliente):
    """CP-09: correo que no es del dominio corporativo."""
    antes = total(cliente)
    r = cliente.post("/api/empleados", json=datos_validos(correo=f"ana.{uuid.uuid4().hex[:10]}@gmail.com"))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "Usa el correo corporativo @empresa.com"
    assert total(cliente) == antes


def test_cp_11_fecha_futura(cliente):
    """CP-11: fecha de ingreso futura."""
    antes = total(cliente)
    r = cliente.post(
        "/api/empleados",
        json=datos_validos(nombre="Pedro Gil", correo=correo_unico("pedro"), puesto="Operador",
                           departamento="Operaciones", fecha_ingreso="2099-01-01"),
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "La fecha de ingreso no puede ser futura"
    assert total(cliente) == antes


def test_cp_13_nombre_corto(cliente):
    """CP-13: nombre demasiado corto."""
    antes = total(cliente)
    r = cliente.post("/api/empleados", json=datos_validos(nombre="A", departamento="Tecnología"))
    afirma_422_campo(r, "nombre")
    assert total(cliente) == antes


def test_cp_15_puesto_vacio(cliente):
    """CP-15: puesto vacío."""
    antes = total(cliente)
    r = cliente.post(
        "/api/empleados",
        json=datos_validos(nombre="Sofía Mena", puesto="", departamento="Recursos Humanos"),
    )
    afirma_422_campo(r, "puesto")
    assert total(cliente) == antes


def test_cp_17_departamento_fuera_catalogo(cliente):
    """CP-17: departamento fuera de la lista permitida."""
    assert "Marketing" not in cliente.get("/api/departamentos").json()
    antes = total(cliente)
    r = cliente.post("/api/empleados", json=datos_validos(nombre="Raúl Vega", departamento="Marketing"))
    afirma_422_campo(r, "departamento")
    assert total(cliente) == antes


def test_cp_19_falta_fecha_ingreso(cliente):
    """CP-19: fecha de ingreso ausente."""
    antes = total(cliente)
    datos = datos_validos(nombre="Eva Lara", departamento="Ventas")
    del datos["fecha_ingreso"]
    r = cliente.post("/api/empleados", json=datos)
    afirma_422_campo(r, "fecha_ingreso")
    assert total(cliente) == antes
