"""Pruebas de API de HU-03: edición y baja de empleados (casos CP impares)."""
import uuid

import httpx
import pytest

MENSAJE_BAJA = "No se puede editar a un empleado dado de baja"


@pytest.fixture
def cliente(url_api):
    with httpx.Client(base_url=url_api, timeout=10) as c:
        yield c


def crear(cliente, puesto="Analista", departamento="Ventas", fecha_ingreso="2024-03-01") -> dict:
    """Crea un empleado activo con correo único y devuelve la respuesta JSON."""
    correo = f"emp.{uuid.uuid4().hex[:12]}@empresa.com"
    r = cliente.post("/api/empleados", json={
        "nombre": f"Ana López {uuid.uuid4().hex[:8]}", "correo": correo, "puesto": puesto,
        "departamento": departamento, "fecha_ingreso": fecha_ingreso,
    })
    assert r.status_code == 201, r.text
    return r.json()


def obtener(cliente, emp) -> dict:
    r = cliente.get(f"/api/empleados/{emp['id']}")
    assert r.status_code == 200, r.text
    return r.json()


def test_cp_01_editar_puesto_y_departamento(cliente):
    """CP-01: editar puesto y departamento de un empleado activo."""
    emp = crear(cliente)
    r = cliente.put(f"/api/empleados/{emp['id']}", json={"puesto": "Líder de Finanzas", "departamento": "Finanzas"})
    assert r.status_code == 200, r.text
    e = obtener(cliente, emp)
    assert e["puesto"] == "Líder de Finanzas"
    assert e["departamento"] == "Finanzas"
    assert e["numero_empleado"] == emp["numero_empleado"]
    assert e["correo"] == emp["correo"]
    assert e["estado"] == "activo"


def test_cp_03_rechazar_departamento_invalido(cliente):
    """CP-03: rechazar un departamento fuera de la lista permitida."""
    emp = crear(cliente, departamento="Ventas")
    r = cliente.put(f"/api/empleados/{emp['id']}", json={"puesto": "Analista", "departamento": "Marketing"})
    assert r.status_code == 422, r.text
    assert "departamento" in str(r.json()["detail"])
    assert obtener(cliente, emp)["departamento"] == "Ventas"


def test_cp_05_rechazar_puesto_de_un_caracter(cliente):
    """CP-05: rechazar un puesto de un solo carácter."""
    emp = crear(cliente)
    r = cliente.put(f"/api/empleados/{emp['id']}", json={"puesto": "A", "departamento": "Ventas"})
    assert r.status_code == 422, r.text
    assert "puesto" in str(r.json()["detail"])
    assert obtener(cliente, emp)["puesto"] == "Analista"


def test_cp_07_rechazar_puesto_de_mas_de_60(cliente):
    """CP-07: rechazar un puesto de más de 60 caracteres."""
    emp = crear(cliente)
    r = cliente.put(f"/api/empleados/{emp['id']}", json={"puesto": "A" * 61, "departamento": "Ventas"})
    assert r.status_code == 422, r.text
    assert "puesto" in str(r.json()["detail"])
    assert obtener(cliente, emp)["puesto"] == "Analista"


def test_cp_09_dar_de_baja_empleado_activo(cliente):
    """CP-09: dar de baja a un empleado activo."""
    emp = crear(cliente)
    r = cliente.post(f"/api/empleados/{emp['id']}/baja", json={"fecha_baja": "2026-10-15"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "baja"
    assert cuerpo["fecha_baja"] == "2026-10-15"
    lista = cliente.get("/api/empleados").json()
    assert emp["id"] in {e["id"] for e in lista}


def test_cp_11_rechazar_baja_anterior_al_ingreso(cliente):
    """CP-11: rechazar una fecha de baja anterior a la fecha de ingreso."""
    emp = crear(cliente, fecha_ingreso="2024-03-01")
    r = cliente.post(f"/api/empleados/{emp['id']}/baja", json={"fecha_baja": "2024-02-28"})
    assert r.status_code == 422, r.text
    assert "fecha_baja" in str(r.json()["detail"])
    e = obtener(cliente, emp)
    assert e["estado"] == "activo"
    assert e["fecha_baja"] is None


def test_cp_13_no_editar_empleado_de_baja(cliente):
    """CP-13: no se puede editar a un empleado dado de baja."""
    emp = crear(cliente)
    r = cliente.post(f"/api/empleados/{emp['id']}/baja", json={"fecha_baja": "2026-10-15"})
    assert r.status_code == 200, r.text
    r = cliente.put(f"/api/empleados/{emp['id']}", json={"puesto": "Gerente", "departamento": "Ventas"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == MENSAJE_BAJA
    assert obtener(cliente, emp)["puesto"] == "Analista"
