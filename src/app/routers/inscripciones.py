"""Router para registro y consulta de inscripciones."""
from typing import Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from src.app.services.inscripciones_service import (
    inscribir_usuario,
    obtener_mis_inscripciones,
)

router = APIRouter(tags=["inscripciones"])


@router.post("/inscripciones")
async def post_inscripcion(request: Request):
    try:
        cuerpo = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "cuerpo JSON invalido"})

    tabla_eventos = request.app.state.tabla_eventos
    tabla_inscr = request.app.state.tabla_inscripciones
    sns = request.app.state.sns_client

    status_code, resultado = inscribir_usuario(
        cuerpo, tabla_eventos, tabla_inscr, sns
    )
    return JSONResponse(status_code=status_code, content=resultado)


@router.get("/inscripciones")
def get_mis_inscripciones(
    request: Request,
    email: Optional[str] = Query(None, description="Email del participante"),
):
    tabla_inscr = request.app.state.tabla_inscripciones
    status_code, resultado = obtener_mis_inscripciones(email, tabla_inscr)
    return JSONResponse(status_code=status_code, content=resultado)
