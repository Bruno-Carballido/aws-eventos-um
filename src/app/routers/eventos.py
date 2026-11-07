"""Router para el catálogo de eventos."""
from fastapi import APIRouter, Request

from src.app.services.eventos_service import listar_eventos

router = APIRouter(tags=["eventos"])


@router.get("/eventos")
def get_eventos(request: Request):
    tabla_eventos = request.app.state.tabla_eventos
    return listar_eventos(tabla_eventos)
