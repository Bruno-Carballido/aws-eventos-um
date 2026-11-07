import json
import os
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")


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
    if evento["fecha"] < datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"):
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
            "creadoEn": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )

    _confirmar_por_email(evento_id, evento["titulo"], email, nombre)

    return _resp(201, {"inscripcionId": inscripcion_id, "estado": "confirmacion_enviada"})


def _confirmar_por_email(evento_id, titulo, email, nombre):
    """Un topic por evento: solo los inscriptos de ESTE evento reciben sus correos."""
    topic_arn = _topic_del_evento(evento_id)
    # La suscripcion llega como email de confirmacion de SNS (un clic del usuario)
    sns.subscribe(
        TopicArn=topic_arn, Protocol="email", Endpoint=email,
        ReturnArn=True,
    )
    sns.publish(
        TopicArn=topic_arn,
        Subject="Inscripcion confirmada",
        Message=f"Hola {nombre}: quedaste inscripto a '{titulo}'. Recibiras un recordatorio antes del evento.",
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
