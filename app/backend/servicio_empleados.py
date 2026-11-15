"""Lógica de negocio de empleados."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from esquemas import BajaEmpleado, EmpleadoCrear, EmpleadoEditar
from modelos import Empleado


def crear_empleado(sesion: Session, datos: EmpleadoCrear) -> Empleado:
    correo = datos.correo.lower()
    if not correo.endswith("@empresa.com") or correo == "@empresa.com":
        raise HTTPException(422, "Usa el correo corporativo @empresa.com")
    if datos.fecha_ingreso > date.today():
        raise HTTPException(422, "La fecha de ingreso no puede ser futura")
    existe = sesion.scalar(select(Empleado).where(func.lower(Empleado.correo) == correo))
    if existe:
        raise HTTPException(409, "El correo ya está registrado")

    empleado = Empleado(
        nombre=datos.nombre,
        correo=correo,
        puesto=datos.puesto,
        departamento=datos.departamento,
        fecha_ingreso=datos.fecha_ingreso,
        estado="activo",
    )
    sesion.add(empleado)
    try:
        sesion.flush()
        empleado.numero_empleado = f"EMP-{empleado.id:04d}"
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise HTTPException(409, "El correo ya está registrado")
    return empleado


MENSAJE_EMPLEADO_EN_BAJA = "No se puede editar a un empleado dado de baja"


def editar_empleado(sesion: Session, id_empleado: int, datos: EmpleadoEditar) -> Empleado:
    empleado = obtener_empleado(sesion, id_empleado)
    if empleado.estado == "baja":
        raise HTTPException(409, MENSAJE_EMPLEADO_EN_BAJA)
    empleado.puesto = datos.puesto
    empleado.departamento = datos.departamento
    sesion.commit()
    return empleado


def dar_de_baja(sesion: Session, id_empleado: int, datos: BajaEmpleado) -> Empleado:
    empleado = obtener_empleado(sesion, id_empleado)
    if empleado.estado == "baja":
        raise HTTPException(409, MENSAJE_EMPLEADO_EN_BAJA)
    if datos.fecha_baja < empleado.fecha_ingreso:
        raise HTTPException(422, "Corrige el campo: fecha de baja")
    empleado.estado = "baja"
    empleado.fecha_baja = datos.fecha_baja
    sesion.commit()
    return empleado


def listar_empleados(sesion: Session, q: str | None, departamento: str | None):
    consulta = select(Empleado).order_by(Empleado.id)
    if departamento:
        consulta = consulta.where(Empleado.departamento == departamento)
    empleados = list(sesion.scalars(consulta))
    if q and q.strip():
        # casefold en Python: lower() de SQLite no maneja acentos en mayúsculas
        aguja = q.strip().casefold()
        empleados = [
            e for e in empleados
            if aguja in (e.nombre or "").casefold()
            or aguja in (e.correo or "").casefold()
            or aguja in (e.numero_empleado or "").casefold()
        ]
    return empleados


def obtener_empleado(sesion: Session, id_empleado: int) -> Empleado:
    empleado = sesion.get(Empleado, id_empleado)
    if not empleado:
        raise HTTPException(404, "Empleado no encontrado")
    return empleado
