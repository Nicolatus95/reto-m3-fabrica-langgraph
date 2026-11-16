"""Pruebas de API de HU-04: jefe directo de un empleado (casos CP impares)."""
import uuid

import httpx
import pytest

M_PROPIO = "Un empleado no puede ser su propio jefe"
M_NO_EXISTE = "El jefe indicado no existe"
M_BAJA = "Un empleado dado de baja no puede ser jefe"
M_CICLO = "La asignación crearía un ciclo en la línea de reporte"


@pytest.fixture
def cliente(url_api):
    with httpx.Client(base_url=url_api, timeout=10) as c:
        yield c


def crear(cliente, nombre="Persona") -> dict:
    """Crea un empleado activo con correo único."""
    r = cliente.post("/api/empleados", json={
        "nombre": f"{nombre} {uuid.uuid4().hex[:8]}",
        "correo": f"emp.{uuid.uuid4().hex[:12]}@empresa.com",
        "puesto": "Analista", "departamento": "Ventas", "fecha_ingreso": "2024-03-01",
    })
    assert r.status_code == 201, r.text
    return r.json()


def asignar(cliente, emp, jefe_id):
    return cliente.put(f"/api/empleados/{emp['id']}", json={"jefe_id": jefe_id})


def obtener(cliente, emp) -> dict:
    r = cliente.get(f"/api/empleados/{emp['id']}")
    assert r.status_code == 200, r.text
    return r.json()


def test_cp_01_asignar_jefe_activo(cliente):
    """CP-01: asignar como jefe a un empleado activo."""
    ana, luis = crear(cliente, "Ana"), crear(cliente, "Luis")
    r = asignar(cliente, luis, ana["id"])
    assert r.status_code == 200, r.text
    assert obtener(cliente, luis)["jefe_id"] == ana["id"]


def test_cp_03_ver_jefe_en_listado(cliente):
    """CP-03: el listado expone al jefe del empleado."""
    ana, luis = crear(cliente, "Ana"), crear(cliente, "Luis")
    assert asignar(cliente, luis, ana["id"]).status_code == 200
    r = cliente.get("/api/empleados")
    assert r.status_code == 200, r.text
    fila = next(e for e in r.json() if e["id"] == luis["id"])
    assert fila["jefe_id"] == ana["id"]
    assert fila["jefe_nombre"] == ana["nombre"]


def test_cp_05_quitar_jefe(cliente):
    """CP-05: quitar el jefe de un empleado."""
    ana, luis = crear(cliente, "Ana"), crear(cliente, "Luis")
    assert asignar(cliente, luis, ana["id"]).status_code == 200
    r = asignar(cliente, luis, None)
    assert r.status_code == 200, r.text
    assert obtener(cliente, luis)["jefe_id"] is None


def test_cp_07_rechazar_propio_jefe(cliente):
    """CP-07: rechazar que un empleado sea su propio jefe."""
    ana = crear(cliente, "Ana")
    r = asignar(cliente, ana, ana["id"])
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == M_PROPIO
    assert obtener(cliente, ana)["jefe_id"] is None


def test_cp_09_rechazar_jefe_inexistente(cliente):
    """CP-09: rechazar un jefe que no existe."""
    luis = crear(cliente, "Luis")
    r = asignar(cliente, luis, 999999)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == M_NO_EXISTE
    assert obtener(cliente, luis)["jefe_id"] is None


def test_cp_10_rechazar_jefe_de_baja(cliente):
    """CP-10: rechazar un jefe dado de baja."""
    luis, marta = crear(cliente, "Luis"), crear(cliente, "Marta")
    r = cliente.post(f"/api/empleados/{marta['id']}/baja", json={"fecha_baja": "2026-11-15"})
    assert r.status_code == 200, r.text
    r = asignar(cliente, luis, marta["id"])
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == M_BAJA
    assert obtener(cliente, luis)["jefe_id"] is None


def test_cp_11_rechazar_ciclo_directo(cliente):
    """CP-11: rechazar un ciclo directo en la línea de reporte."""
    ana, luis = crear(cliente, "Ana"), crear(cliente, "Luis")
    assert asignar(cliente, luis, ana["id"]).status_code == 200
    r = asignar(cliente, ana, luis["id"])
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == M_CICLO
    assert obtener(cliente, ana)["jefe_id"] is None


def test_cp_12_rechazar_ciclo_indirecto(cliente):
    """CP-12: rechazar un ciclo indirecto en la línea de reporte."""
    ana, luis, eva = crear(cliente, "Ana"), crear(cliente, "Luis"), crear(cliente, "Eva")
    assert asignar(cliente, luis, ana["id"]).status_code == 200
    assert asignar(cliente, eva, luis["id"]).status_code == 200
    r = asignar(cliente, ana, eva["id"])
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == M_CICLO
    assert obtener(cliente, ana)["jefe_id"] is None


def test_cp_13_baja_de_jefe_libera_subordinados(cliente):
    """CP-13: al dar de baja a un jefe sus subordinados quedan sin jefe."""
    ana, luis, eva = crear(cliente, "Ana"), crear(cliente, "Luis"), crear(cliente, "Eva")
    assert asignar(cliente, luis, ana["id"]).status_code == 200
    assert asignar(cliente, eva, ana["id"]).status_code == 200
    r = cliente.post(f"/api/empleados/{ana['id']}/baja", json={"fecha_baja": "2026-11-15"})
    assert r.status_code == 200, r.text
    assert obtener(cliente, ana)["estado"] == "baja"
    assert obtener(cliente, luis)["jefe_id"] is None
    assert obtener(cliente, eva)["jefe_id"] is None
