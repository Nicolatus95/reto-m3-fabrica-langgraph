"""Esquemas Pydantic de entrada y salida."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modelos import DEPARTAMENTOS

Departamento = Literal["Tecnología", "Ventas", "Finanzas", "Recursos Humanos", "Operaciones"]


class EmpleadoCrear(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    correo: str = Field(min_length=1, max_length=255)
    puesto: str = Field(min_length=2, max_length=60)
    departamento: Departamento
    fecha_ingreso: date

    @field_validator("nombre", "puesto", mode="before")
    @classmethod
    def _recortar(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("correo", mode="before")
    @classmethod
    def _correo(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class EmpleadoEditar(BaseModel):
    """Solo puesto y departamento son editables; los campos extra se ignoran."""
    puesto: str = Field(min_length=2, max_length=60)
    departamento: Departamento

    @field_validator("puesto", mode="before")
    @classmethod
    def _recortar(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class BajaEmpleado(BaseModel):
    fecha_baja: date


class EmpleadoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_empleado: str
    nombre: str
    correo: str
    puesto: str
    departamento: str
    fecha_ingreso: date
    estado: str
    fecha_baja: date | None = None
    creado_en: datetime
