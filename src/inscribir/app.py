import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
UTC_MONTEVIDEO = timedelta(hours=-3)  # Uruguay no usa horario de verano desde 2015


def fecha_legible(fecha_iso):
    """'2026-11-09T18:00:00Z' -> 'lunes 9 de noviembre de 2026, 15:00 h' (hora de Montevideo)."""
    dt = datetime.strptime(fecha_iso, "%Y-%m-%dT%H:%M:%SZ") + UTC_MONTEVIDEO
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} de {dt.year}, {dt:%H:%M} h"


def handler(event, context):
    try:
        cuerpo = json.loads(event.get("body") or "{}")
        evento_id = cuerpo["eventoId"]
        nombre = cuerpo["nombre"].strip()
        email = cuerpo["email"].strip().lower()
    except (KeyError, AttributeError, ValueError):
        return _resp(400, {"error": "faltan campos: eventoId, nombre, email"})

    tabla_eventos = dynamodb.Table(os.environ["TABLA_EVENTOS"])
    tabla_inscr = dynamodb.Table(os.environ["TABLA_INSCRIPCIONES"])

    evento = tabla_eventos.get_item(Key={"eventoId": evento_id}).get("Item")
    if not evento:
        return _resp(404, {"error": "evento inexistente"})
    if evento["fecha"] < datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"):
        return _resp(400, {"error": "el evento ya ocurrio"})

    # Evita inscripciones duplicadas del mismo email en el mismo evento
    existentes = tabla_inscr.query(
        IndexName="porEvento",
        KeyConditionExpression="eventoId = :e",
        FilterExpression="email = :m",
        ExpressionAttributeValues={":e": evento_id, ":m": email},
    )
    if existentes.get("Items"):
        return _resp(409, {"error": "ya esta inscripto en este evento"})

    # Cupo: incremento condicional atomico; si se lleno, responde 409 sin insertar.
    # Evento sin atributo "cupo" = sin limite.
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
                return _resp(409, {"error": "sin cupos disponibles"})
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
        evento_id, evento["titulo"], email, nombre, evento["fecha"], evento.get("lugar", "")
    )

    return _resp(201, {"inscripcionId": inscripcion_id, "estado": "confirmacion_enviada"})


def _confirmar_por_email(evento_id, titulo, email, nombre, fecha, lugar):
    """Un topic por evento: solo los inscriptos de ESTE evento reciben sus correos."""
    topic_arn = _topic_del_evento(evento_id)
    # La suscripcion llega como email de confirmacion de SNS (un clic del usuario)
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


def _topic_del_evento(evento_id):
    nombre = f"evento-{evento_id}"
    existentes = sns.list_topics().get("Topics", [])
    for t in existentes:
        if t["TopicArn"].rstrip("/").endswith(nombre):
            return t["TopicArn"]
    return sns.create_topic(Name=nombre)["TopicArn"]


def _resp(code, payload):
    return {"statusCode": code, "body": json.dumps(payload)}
