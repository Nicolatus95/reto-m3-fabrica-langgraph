"""Rutas de /api/empleados."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import obtener_sesion
from modelos import Empleado
from schemas import BajaEntrada, EmpleadoCrear, EmpleadoEditar, EmpleadoSalida

router = APIRouter(prefix="/empleados", tags=["empleados"])

DOMINIO = "@empresa.com"


@router.get("", response_model=list[EmpleadoSalida])
def listar_empleados(
    buscar: str | None = Query(None),
    departamento: str | None = Query(None),
    sesion: Session = Depends(obtener_sesion),
):
    consulta = select(Empleado).order_by(Empleado.id)
    if departamento:
        consulta = consulta.where(Empleado.departamento == departamento)
    empleados = sesion.scalars(consulta).all()
    texto = (buscar or "").strip().casefold()
    if texto:
        # casefold en Python: lower() de SQLite no maneja acentos
        empleados = [
            e for e in empleados
            if texto in e.nombre.casefold() or texto in e.correo.casefold()
        ]
    return empleados


MENSAJE_EN_BAJA = "No se puede editar a un empleado dado de baja"


def _obtener_o_404(sesion: Session, id: int) -> Empleado:
    empleado = sesion.get(Empleado, id)
    if empleado is None:
        raise HTTPException(404, "Empleado no encontrado")
    return empleado


@router.get("/{id}", response_model=EmpleadoSalida)
def obtener_empleado(id: int, sesion: Session = Depends(obtener_sesion)):
    return _obtener_o_404(sesion, id)


@router.put("/{id}", response_model=EmpleadoSalida)
def editar_empleado(id: int, datos: EmpleadoEditar, sesion: Session = Depends(obtener_sesion)):
    empleado = _obtener_o_404(sesion, id)
    if empleado.estado == "baja":
        raise HTTPException(409, MENSAJE_EN_BAJA)
    empleado.puesto = datos.puesto
    empleado.departamento = datos.departamento
    sesion.commit()
    sesion.refresh(empleado)
    return empleado


@router.post("/{id}/baja", response_model=EmpleadoSalida)
def dar_de_baja(id: int, datos: BajaEntrada, sesion: Session = Depends(obtener_sesion)):
    empleado = _obtener_o_404(sesion, id)
    if empleado.estado == "baja":
        raise HTTPException(409, MENSAJE_EN_BAJA)
    if datos.fecha_baja < empleado.fecha_ingreso:
        raise HTTPException(422, "Corrige el campo: fecha_baja")
    empleado.estado = "baja"
    empleado.fecha_baja = datos.fecha_baja
    sesion.commit()
    sesion.refresh(empleado)
    return empleado


@router.post("", response_model=EmpleadoSalida, status_code=201)
def registrar_empleado(datos: EmpleadoCrear, sesion: Session = Depends(obtener_sesion)):
    correo = datos.correo.lower()
    if not correo.endswith(DOMINIO) or len(correo) == len(DOMINIO):
        raise HTTPException(422, "Usa el correo corporativo @empresa.com")
    if datos.fecha_ingreso > date.today():
        raise HTTPException(422, "La fecha de ingreso no puede ser futura")
    existe = sesion.scalar(select(Empleado.id).where(func.lower(Empleado.correo) == correo))
    if existe is not None:
        raise HTTPException(409, "El correo ya está registrado")

    siguiente = (sesion.scalar(select(func.max(Empleado.id))) or 0) + 1
    empleado = Empleado(
        numero_empleado=f"EMP-{siguiente:04d}",
        nombre=datos.nombre,
        correo=correo,
        puesto=datos.puesto,
        departamento=datos.departamento,
        fecha_ingreso=datos.fecha_ingreso,
        estado="activo",
    )
    sesion.add(empleado)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise HTTPException(409, "El correo ya está registrado")
    return empleado
