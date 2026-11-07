"""Carga eventos de prueba en DynamoDB Local o en la tabla real.
Uso: python scripts/seed_eventos.py [--tabla Eventos]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import boto3

EVENTOS = [
    {
        "eventoId": "e-001",
        "titulo": "Charla de AWS en la UM",
        "descripcion": "Introduccion a contenedores con ECS Fargate y balanceo con ALB.",
        "lugar": "Aula 101, Universidad de Montevideo",
        "cupo": 30,
        "fecha": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT18:00:00Z"),
    },
    {
        "eventoId": "e-002",
        "titulo": "Taller de DynamoDB",
        "descripcion": "Modelado de datos y consultas con GSIs.",
        "lugar": "Laboratorio B, UM",
        "cupo": 25,
        "fecha": (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT19:00:00Z"),
    },
    {
        "eventoId": "e-003",
        "titulo": "Meetup de Cloud Practitioner",
        "descripcion": "Preparacion para la certificacion.",
        "lugar": "Montevideo",
        "cupo": 10,
        "fecha": (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT20:00:00Z"),
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tabla", default=os.environ.get("TABLA_EVENTOS", "Eventos"))
    parser.add_argument("--local", action="store_true", help="DynamoDB Local en :8000")
    args = parser.parse_args()

    if args.local:
        dynamodb = boto3.resource("dynamodb", endpoint_url="http://localhost:8000")
    else:
        dynamodb = boto3.resource("dynamodb")
    tabla = dynamodb.Table(args.tabla)
    for e in EVENTOS:
        tabla.put_item(Item=e)
        print("cargado:", e["eventoId"], e["titulo"])


if __name__ == "__main__":
    sys.exit(main())
