"""Modelos de base de datos."""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

DEPARTAMENTOS = ["Tecnología", "Ventas", "Finanzas", "Recursos Humanos", "Operaciones"]


class Empleado(Base):
    __tablename__ = "empleados"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_empleado: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    nombre: Mapped[str] = mapped_column(String(80))
    correo: Mapped[str] = mapped_column(String(255), unique=True)
    puesto: Mapped[str] = mapped_column(String(60))
    departamento: Mapped[str] = mapped_column(String(40))
    fecha_ingreso: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(10), default="activo")
    fecha_baja: Mapped[date | None] = mapped_column(Date, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    jefe_id: Mapped[int | None] = mapped_column(
        ForeignKey("empleados.id"), nullable=True, default=None
    )
