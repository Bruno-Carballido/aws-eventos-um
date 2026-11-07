import json
import os
from datetime import datetime, timedelta, timezone

import boto3

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

VENTANA_HORAS = 24  # recordatorio para eventos que ocurren en las proximas 24 h

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
UTC_MONTEVIDEO = timedelta(hours=-3)  # Uruguay no usa horario de verano desde 2015


def fecha_legible(fecha_iso):
    """'2026-11-09T18:00:00Z' -> 'lunes 9 de noviembre de 2026, 15:00 h' (hora de Montevideo)."""
    dt = datetime.strptime(fecha_iso, "%Y-%m-%dT%H:%M:%SZ") + UTC_MONTEVIDEO
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} de {dt.year}, {dt:%H:%M} h"


def construir_recordatorio(titulo, fecha, lugar):
    texto = (
        "Hola,\n\n"
        f"Te recordamos que mañana tenés «{titulo}».\n\n"
        f"Fecha: {fecha_legible(fecha)}\n"
        f"Lugar: {lugar or 'a confirmar'}\n\n"
        "¡Te esperamos!\n"
        "Equipo de Eventos UM"
    )
    return texto, f"Recordatorio: {titulo}"


def handler(event, context):
    tabla = dynamodb.Table(os.environ["TABLA_EVENTOS"])
    ahora = datetime.now(timezone.utc)
    limite = (ahora + timedelta(hours=VENTANA_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Scan acotado por diseño; con catalogo grande se reemplaza por un GSI de fecha
    proximos = [
        e for e in tabla.scan(ProjectionExpression="eventoId,titulo,fecha,lugar,notificado").get("Items", [])
        if ahora.strftime("%Y-%m-%dT%H:%M:%SZ") <= e["fecha"] <= limite
    ]

    enviados = []
    for e in proximos:
        # Anti-repeticion: el item marca notificado=fecha-del-ultimo-envio
        if e.get("notificado") == e["fecha"]:
            continue
        topic = _topic_del_evento(e["eventoId"])
        if not topic:
            continue
        texto, asunto = construir_recordatorio(e["titulo"], e["fecha"], e.get("lugar", ""))
        sns.publish(TopicArn=topic, Subject=asunto, Message=texto)
        tabla.update_item(
            Key={"eventoId": e["eventoId"]},
            UpdateExpression="SET notificado = :f",
            ExpressionAttributeValues={":f": e["fecha"]},
        )
        enviados.append(e["eventoId"])

    print(json.dumps({"evento": "recordatorio", "enviados": enviados}))
    return {"statusCode": 200, "enviados": enviados}


def _topic_del_evento(evento_id):
    nombre = f"evento-{evento_id}"
    for t in sns.list_topics().get("Topics", []):
        if t["TopicArn"].rstrip("/").endswith(nombre):
            return t["TopicArn"]
    return None
