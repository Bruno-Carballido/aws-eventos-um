"""Servicio para registro y consulta de inscripciones."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
UTC_MONTEVIDEO = timedelta(hours=-3)


def fecha_legible(fecha_iso: str) -> str:
    """'2026-11-09T18:00:00Z' -> 'lunes 9 de noviembre de 2026, 15:00 h'."""
    dt = datetime.strptime(fecha_iso, "%Y-%m-%dT%H:%M:%SZ") + UTC_MONTEVIDEO
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} de {dt.year}, {dt:%H:%M} h"


def inscribir_usuario(
    cuerpo: dict, tabla_eventos: Any, tabla_inscr: Any, sns_client: Any
) -> tuple[int, dict]:
    try:
        evento_id = cuerpo["eventoId"]
        nombre = cuerpo["nombre"].strip()
        email = cuerpo["email"].strip().lower()
        if not nombre or not email or not EMAIL_RE.match(email):
            return 400, {"error": "faltan campos: eventoId, nombre, email"}
    except (KeyError, AttributeError, TypeError):
        return 400, {"error": "faltan campos: eventoId, nombre, email"}

    evento = tabla_eventos.get_item(Key={"eventoId": evento_id}).get("Item")
    if not evento:
        return 404, {"error": "evento inexistente"}
    if evento["fecha"] < datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"):
        return 400, {"error": "el evento ya ocurrio"}

    # Evita inscripciones duplicadas del mismo email en el mismo evento
    existentes = tabla_inscr.query(
        IndexName="porEvento",
        KeyConditionExpression="eventoId = :e",
        FilterExpression="email = :m",
        ExpressionAttributeValues={":e": evento_id, ":m": email},
    )
    if existentes.get("Items"):
        return 409, {"error": "ya esta inscripto en este evento"}

    # Cupo: incremento condicional atómico
    if "cupo" in evento:
        try:
            tabla_eventos.update_item(
                Key={"eventoId": evento_id},
                UpdateExpression="ADD inscritos :uno",
                ConditionExpression="attribute_not_exists(inscritos) OR inscritos < :cupo",
                ExpressionAttributeValues={":uno": 1, ":cupo": int(evento["cupo"])},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return 409, {"error": "sin cupos disponibles"}
            raise

    inscripcion_id = str(uuid.uuid4())
    tabla_inscr.put_item(
        Item={
            "inscripcionId": inscripcion_id,
            "eventoId": evento_id,
            "email": email,
            "nombre": nombre,
            "tituloEvento": evento["titulo"],
            "creadoEn": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )

    _confirmar_por_email(
        sns_client, evento_id, evento["titulo"], email, nombre, evento["fecha"], evento.get("lugar", "")
    )

    return 201, {"inscripcionId": inscripcion_id, "estado": "confirmacion_enviada"}


def obtener_mis_inscripciones(email: str, tabla_inscr: Any) -> tuple[int, list[dict] | dict]:
    email_normalizado = (email or "").strip().lower()
    if not email_normalizado or not EMAIL_RE.match(email_normalizado):
        return 400, {"error": "falta el parametro email o su formato es invalido"}

    resp = tabla_inscr.query(
        IndexName="porEmail",
        KeyConditionExpression="email = :m",
        ExpressionAttributeValues={":m": email_normalizado},
    )
    items = resp.get("Items", [])
    items.sort(key=lambda i: i.get("creadoEn", ""), reverse=True)
    return 200, items


def _confirmar_por_email(sns, evento_id, titulo, email, nombre, fecha, lugar):
    topic_arn = _topic_del_evento(sns, evento_id)
    sns.subscribe(
        TopicArn=topic_arn, Protocol="email", Endpoint=email,
        ReturnSubscriptionArn=True,
    )
    sns.publish(
        TopicArn=topic_arn,
        Subject=f"Inscripción confirmada: {titulo}",
        Message=(
            f"Hola {nombre},\n\n"
            f"Tu inscripción a «{titulo}» está confirmada.\n\n"
            f"Fecha: {fecha_legible(fecha)}\n"
            f"Lugar: {lugar or 'a confirmar'}\n\n"
            "Te enviaremos un recordatorio el día anterior al evento.\n\n"
            "Nos vemos ahí.\n"
            "Equipo de Eventos UM"
        ),
    )


def _topic_del_evento(sns, evento_id):
    nombre = f"evento-{evento_id}"
    existentes = sns.list_topics().get("Topics", [])
    for t in existentes:
        if t["TopicArn"].rstrip("/").endswith(nombre):
            return t["TopicArn"]
    return sns.create_topic(Name=nombre)["TopicArn"]
