import json
import os
from decimal import Decimal

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
    # DynamoDB devuelve numeros como Decimal, que json no serializa
    return {"statusCode": 200, "body": json.dumps(items, default=_a_numero)}


def _a_numero(valor):
    if isinstance(valor, Decimal):
        return int(valor) if valor % 1 == 0 else float(valor)
    raise TypeError(f"tipo no serializable: {type(valor).__name__}")
