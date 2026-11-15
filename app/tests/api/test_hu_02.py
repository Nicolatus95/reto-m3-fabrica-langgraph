"""Pruebas de API de HU-02: directorio de empleados, búsqueda y filtros (casos CP impares)."""
import uuid

import httpx
import pytest


@pytest.fixture
def cliente(url_api):
    with httpx.Client(base_url=url_api, timeout=10) as c:
        yield c


def token() -> str:
    return uuid.uuid4().hex[:10]


def crear(cliente, nombre, departamento, puesto="Analista", prefijo="emp", fecha_ingreso="2026-01-10") -> dict:
    """Crea un empleado con correo único y devuelve la respuesta JSON."""
    correo = f"{prefijo}.{uuid.uuid4().hex[:12]}@empresa.com"
    r = cliente.post("/api/empleados", json={
        "nombre": nombre, "correo": correo, "puesto": puesto,
        "departamento": departamento, "fecha_ingreso": fecha_ingreso,
    })
    assert r.status_code == 201, r.text
    return r.json()


def listar(cliente, **params) -> list[dict]:
    r = cliente.get("/api/empleados", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def ids(lista) -> set:
    return {e["id"] for e in lista}


def test_cp_01_directorio_con_datos(cliente):
    """CP-01: ver el directorio con los datos de cada empleado."""
    t = token()
    ana = crear(cliente, f"Ana Torres {t}", "Tecnología", "Analista", "ana")
    luis = crear(cliente, f"Luis Pérez {t}", "Ventas", "Vendedor", "luis")
    lista = {e["id"]: e for e in listar(cliente)}
    for creado, nombre, puesto, depto in [
        (ana, f"Ana Torres {t}", "Analista", "Tecnología"),
        (luis, f"Luis Pérez {t}", "Vendedor", "Ventas"),
    ]:
        e = lista[creado["id"]]
        assert e["numero_empleado"] == creado["numero_empleado"]
        assert e["numero_empleado"].startswith("EMP-")
        assert e["nombre"] == nombre
        assert e["puesto"] == puesto
        assert e["departamento"] == depto
        assert e["estado"] == "activo"


def test_cp_03_buscar_por_nombre(cliente):
    """CP-03: buscar por nombre sin distinguir mayúsculas de minúsculas."""
    t = token()
    ana = crear(cliente, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(cliente, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    resultado = listar(cliente, buscar=f"ANA TORRES {t}".upper())
    assert ids(resultado) == {ana["id"]}
    assert luis["id"] not in ids(resultado)


def test_cp_05_buscar_por_correo(cliente):
    """CP-05: buscar por correo sin distinguir mayúsculas de minúsculas."""
    t = token()
    ana = crear(cliente, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(cliente, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    resultado = listar(cliente, buscar=luis["correo"].swapcase())
    assert ids(resultado) == {luis["id"]}
    assert ana["id"] not in ids(resultado)


def test_cp_07_filtrar_por_departamento(cliente):
    """CP-07: filtrar por departamento."""
    t = token()
    ana = crear(cliente, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(cliente, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    marta = crear(cliente, f"Marta Gil {t}", "Tecnología", prefijo="marta")
    resultado = listar(cliente, departamento="Tecnología")
    assert all(e["departamento"] == "Tecnología" for e in resultado)
    assert {ana["id"], marta["id"]} <= ids(resultado)
    assert luis["id"] not in ids(resultado)


def test_cp_09_busqueda_sin_resultados(cliente):
    """CP-09: búsqueda sin resultados devuelve lista vacía."""
    crear(cliente, f"Ana Torres {token()}", "Tecnología", prefijo="ana")
    assert listar(cliente, buscar=f"Zacarías-{token()}") == []


def test_cp_11_departamento_sin_empleados(cliente):
    """CP-11: filtro por departamento sin empleados devuelve lista vacía (para la búsqueda acotada)."""
    t = token()
    ana = crear(cliente, f"Ana Torres {t}", "Tecnología", prefijo="ana")
    luis = crear(cliente, f"Luis Pérez {t}", "Ventas", prefijo="luis")
    resultado = listar(cliente, departamento="Finanzas")
    assert all(e["departamento"] == "Finanzas" for e in resultado)
    assert not ({ana["id"], luis["id"]} & ids(resultado))
    # Combinado con un texto único, ningún empleado de Finanzas coincide: lista vacía
    assert listar(cliente, departamento="Finanzas", buscar=t) == []


def test_cp_13_empleado_de_baja_sigue_en_directorio(cliente):
    """CP-13: un empleado dado de baja sigue apareciendo en el directorio."""
    marta = crear(cliente, f"Marta Gil {token()}", "Tecnología", prefijo="marta", fecha_ingreso="2026-01-10")
    # Ruta de baja asumida: POST /api/empleados/{id}/baja con fecha_baja
    r = cliente.post(f"/api/empleados/{marta['id']}/baja", json={"fecha_baja": "2026-03-15"})
    assert r.status_code == 200, r.text
    e = {x["id"]: x for x in listar(cliente)}[marta["id"]]
    assert e["numero_empleado"] == marta["numero_empleado"]
    assert e["estado"] == "baja"
    assert e["fecha_baja"] == "2026-03-15"
