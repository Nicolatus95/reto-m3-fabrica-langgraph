"""Aplicación FastAPI de gestión de empleados."""
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sqlalchemy import text

import modelos  # noqa: F401  (registra las tablas)
from database import Base, motor
from routers import departamentos, empleados

Base.metadata.create_all(motor)

# Migración mínima: create_all no agrega columnas a una tabla ya existente
with motor.begin() as conexion:
    columnas = [fila[1] for fila in conexion.execute(text("PRAGMA table_info(empleados)"))]
    if "jefe_id" not in columnas:
        conexion.execute(
            text("ALTER TABLE empleados ADD COLUMN jefe_id INTEGER REFERENCES empleados(id)")
        )

app = FastAPI(title="Gestión de empleados")

api = APIRouter(prefix="/api")
api.include_router(departamentos.router)
api.include_router(empleados.router)
app.include_router(api)


@app.exception_handler(RequestValidationError)
async def error_validacion(request: Request, exc: RequestValidationError):
    campo = "datos"
    for error in exc.errors():
        ubicacion = [p for p in error.get("loc", ()) if p not in ("body", "query", "path")]
        if ubicacion:
            campo = str(ubicacion[0])
            break
    return JSONResponse(
        status_code=422,
        content={"detail": f"Corrige el campo: {campo}", "campo": campo},
    )
