import json
import os
from datetime import datetime, timedelta

import boto3

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

VENTANA_HORAS = 24  # recordatorio para eventos que ocurren en las proximas 24 h


def handler(event, context):
    tabla = dynamodb.Table(os.environ["TABLA_EVENTOS"])
    ahora = datetime.utcnow()
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
        sns.publish(
            TopicArn=topic,
            Subject="Recordatorio: evento manana",
            Message=f"No olvides '{e['titulo']}' — {e['fecha']} en {e.get('lugar', 'lugar a confirmar')}.",
        )
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
