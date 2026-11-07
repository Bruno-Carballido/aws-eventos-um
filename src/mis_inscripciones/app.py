import json
import os

import boto3

dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    email = (params.get("email") or "").strip().lower()
    if not email:
        return _resp(400, {"error": "falta el parametro email"})

    tabla = dynamodb.Table(os.environ["TABLA_INSCRIPCIONES"])
    resp = tabla.query(
        IndexName="porEmail",
        KeyConditionExpression="email = :m",
        ExpressionAttributeValues={":m": email},
    )
    items = resp.get("Items", [])
    items.sort(key=lambda i: i.get("creadoEn", ""), reverse=True)
    return _resp(200, items)


def _resp(code, payload):
    return {"statusCode": code, "body": json.dumps(payload)}