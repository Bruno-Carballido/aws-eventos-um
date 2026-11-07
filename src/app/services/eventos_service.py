"""Servicio para consulta de eventos."""
from decimal import Decimal
from typing import Any


def listar_eventos(tabla_eventos: Any) -> list[dict]:
    """Scan acotado del catálogo de eventos con conversión de Decimal a int/float."""
    resp = tabla_eventos.scan(
        ProjectionExpression="eventoId,titulo,descripcion,fecha,lugar,cupo,inscritos"
    )
    items = resp.get("Items", [])
    for item in items:
        # Un evento recién creado no tiene contador: sin atributo, no hay inscriptos.
        item.setdefault("inscritos", 0)
    items.sort(key=lambda i: i.get("fecha", ""))
    return [_sanitizar_item(item) for item in items]


def _sanitizar_item(item: dict) -> dict:
    resultado = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            resultado[k] = int(v) if v % 1 == 0 else float(v)
        else:
            resultado[k] = v
    return resultado
