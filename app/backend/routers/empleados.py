"""Rutas de /api/empleados."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
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
    return _con_jefe(sesion, empleados)


MENSAJE_EN_BAJA = "No se puede editar a un empleado dado de baja"


def _con_jefe(sesion: Session, empleados: list[Empleado]) -> list[EmpleadoSalida]:
    """Arma la salida con jefe_nombre; los nombres salen de TODOS los empleados."""
    nombres = dict(sesion.execute(select(Empleado.id, Empleado.nombre)).all())
    salidas = []
    for e in empleados:
        salida = EmpleadoSalida.model_validate(e)
        salida.jefe_nombre = nombres.get(e.jefe_id) if e.jefe_id is not None else None
        salidas.append(salida)
    return salidas


def _salida(sesion: Session, empleado: Empleado) -> EmpleadoSalida:
    return _con_jefe(sesion, [empleado])[0]


def _obtener_o_404(sesion: Session, id: int) -> Empleado:
    empleado = sesion.get(Empleado, id)
    if empleado is None:
        raise HTTPException(404, "Empleado no encontrado")
    return empleado


@router.get("/{id}", response_model=EmpleadoSalida)
def obtener_empleado(id: int, sesion: Session = Depends(obtener_sesion)):
    return _salida(sesion, _obtener_o_404(sesion, id))


def _validar_jefe(sesion: Session, id: int, jefe_id: int) -> None:
    if jefe_id == id:
        raise HTTPException(422, "Un empleado no puede ser su propio jefe")
    jefe = sesion.get(Empleado, jefe_id)
    if jefe is None:
        raise HTTPException(422, "El jefe indicado no existe")
    if jefe.estado == "baja":
        raise HTTPException(409, "Un empleado dado de baja no puede ser jefe")
    # Subir por la cadena de jefes desde el jefe propuesto; si aparece id, hay ciclo
    visitados = set()
    actual = jefe
    while actual is not None and actual.id not in visitados:
        if actual.id == id:
            raise HTTPException(422, "La asignación crearía un ciclo en la línea de reporte")
        visitados.add(actual.id)
        actual = sesion.get(Empleado, actual.jefe_id) if actual.jefe_id is not None else None


@router.put("/{id}", response_model=EmpleadoSalida)
def editar_empleado(id: int, datos: EmpleadoEditar, sesion: Session = Depends(obtener_sesion)):
    empleado = _obtener_o_404(sesion, id)
    if empleado.estado == "baja":
        raise HTTPException(409, MENSAJE_EN_BAJA)
    if "jefe_id" in datos.model_fields_set and datos.jefe_id is not None:
        _validar_jefe(sesion, id, datos.jefe_id)
    if datos.puesto is not None:
        empleado.puesto = datos.puesto
    if datos.departamento is not None:
        empleado.departamento = datos.departamento
    if "jefe_id" in datos.model_fields_set:
        empleado.jefe_id = datos.jefe_id
    sesion.commit()
    sesion.refresh(empleado)
    return _salida(sesion, empleado)


@router.post("/{id}/baja", response_model=EmpleadoSalida)
def dar_de_baja(id: int, datos: BajaEntrada, sesion: Session = Depends(obtener_sesion)):
    empleado = _obtener_o_404(sesion, id)
    if empleado.estado == "baja":
        raise HTTPException(409, MENSAJE_EN_BAJA)
    if datos.fecha_baja < empleado.fecha_ingreso:
        raise HTTPException(422, "Corrige el campo: fecha_baja")
    empleado.estado = "baja"
    empleado.fecha_baja = datos.fecha_baja
    # Regla 12: los subordinados quedan sin jefe, en la misma transacción
    sesion.execute(update(Empleado).where(Empleado.jefe_id == id).values(jefe_id=None))
    sesion.commit()
    sesion.refresh(empleado)
    return _salida(sesion, empleado)


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
    return _salida(sesion, empleado)
