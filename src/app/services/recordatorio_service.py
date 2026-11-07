"""Servicio para el envío de recordatorios de eventos."""
from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError

from src.app.services.inscripciones_service import fecha_legible

VENTANA_HORAS = 24


def construir_recordatorio(titulo: str, fecha: str, lugar: str) -> tuple[str, str]:
    texto = (
        "Hola,\n\n"
        f"Te recordamos que mañana tenés «{titulo}».\n\n"
        f"Fecha: {fecha_legible(fecha)}\n"
        f"Lugar: {lugar or 'a confirmar'}\n\n"
        "¡Te esperamos!\n"
        "Equipo de Eventos UM"
    )
    return texto, f"Recordatorio: {titulo}"


def procesar_recordatorios(tabla_eventos: Any, sns_client: Any) -> list[str]:
    ahora = datetime.now(timezone.utc)
    limite = (ahora + timedelta(hours=VENTANA_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    proximos = [
        e for e in tabla_eventos.scan(
            ProjectionExpression="eventoId,titulo,fecha,lugar,notificado"
        ).get("Items", [])
        if ahora.strftime("%Y-%m-%dT%H:%M:%SZ") <= e["fecha"] <= limite
    ]

    enviados = []
    for e in proximos:
        # Anti-repetición: no repetir si ya fue notificado para esta fecha
        if e.get("notificado") == e["fecha"]:
            continue
        topic = _topic_del_evento(sns_client, e["eventoId"])
        if not topic:
            continue
        # Reclamo atómico: si otra tarea ya lo reclamó para esta fecha, no se envía de nuevo.
        if not _reclamar_evento(tabla_eventos, e):
            continue
        texto, asunto = construir_recordatorio(e["titulo"], e["fecha"], e.get("lugar", ""))
        try:
            sns_client.publish(TopicArn=topic, Subject=asunto, Message=texto)
        except Exception:
            _liberar_reclamo(tabla_eventos, e)
            raise
        enviados.append(e["eventoId"])

    return enviados


def _reclamar_evento(tabla_eventos: Any, evento: dict) -> bool:
    """Marca el evento como notificado solo si no lo está para esta fecha.

    Devuelve False si otra ejecución (otra tarea de ECS) ya lo reclamó.
    """
    try:
        tabla_eventos.update_item(
            Key={"eventoId": evento["eventoId"]},
            UpdateExpression="SET notificado = :f",
            ConditionExpression="attribute_not_exists(notificado) OR notificado <> :f",
            ExpressionAttributeValues={":f": evento["fecha"]},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _liberar_reclamo(tabla_eventos: Any, evento: dict) -> None:
    """Quita la marca si la publicación falló, para que la próxima ejecución lo reintente."""
    tabla_eventos.update_item(
        Key={"eventoId": evento["eventoId"]},
        UpdateExpression="REMOVE notificado",
        ConditionExpression="notificado = :f",
        ExpressionAttributeValues={":f": evento["fecha"]},
    )


def _topic_del_evento(sns, evento_id):
    nombre = f"evento-{evento_id}"
    for t in sns.list_topics().get("Topics", []):
        if t["TopicArn"].rstrip("/").endswith(nombre):
            return t["TopicArn"]
    return None
