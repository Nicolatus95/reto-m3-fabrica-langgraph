"""Rutas de /api/departamentos y salud."""
from fastapi import APIRouter

from modelos import DEPARTAMENTOS

router = APIRouter(tags=["catálogos"])


@router.get("/departamentos")
def listar_departamentos():
    return DEPARTAMENTOS


@router.get("/salud")
def salud():
    return {"estado": "ok"}
