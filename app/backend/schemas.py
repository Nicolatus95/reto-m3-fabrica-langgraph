"""Esquemas Pydantic de empleados."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Puesto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
Correo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]

Departamento = Literal["Tecnología", "Ventas", "Finanzas", "Recursos Humanos", "Operaciones"]


class EmpleadoCrear(BaseModel):
    nombre: Nombre
    correo: Correo
    puesto: Puesto
    departamento: Departamento
    fecha_ingreso: date


class EmpleadoEditar(BaseModel):
    """Puesto, departamento y jefe son editables; None en puesto/departamento = sin cambio.
    jefe_id: se distingue «no enviado» de «null» con model_fields_set."""
    puesto: Puesto | None = None
    departamento: Departamento | None = None
    jefe_id: int | None = None


class BajaEntrada(BaseModel):
    fecha_baja: date


class EmpleadoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_empleado: str | None
    nombre: str
    correo: str
    puesto: str
    departamento: str
    fecha_ingreso: date
    estado: str
    fecha_baja: date | None
    creado_en: datetime
    jefe_id: int | None = None
    jefe_nombre: str | None = None
