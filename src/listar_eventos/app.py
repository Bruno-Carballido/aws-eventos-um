import json
import os
import boto3

dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    tabla = dynamodb.Table(os.environ["TABLA_EVENTOS"])
    # Scan acotado: catalogo de pruebas, bajo consumo
    resp = tabla.scan(
        ProjectionExpression="eventoId,titulo,descripcion,fecha,lugar,cupo,inscritos"
    )
    items = resp.get("Items", [])
    items.sort(key=lambda i: i.get("fecha", ""))
    return {"statusCode": 200, "body": json.dumps(items)}
