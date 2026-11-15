"""Conexión a la base de datos SQLite."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

CARPETA_DATOS = Path(__file__).resolve().parent / "datos"
CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

motor = create_engine(
    f"sqlite:///{CARPETA_DATOS / 'empleados.db'}",
    connect_args={"check_same_thread": False},
)
SesionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def obtener_sesion():
    sesion = SesionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
