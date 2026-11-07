"""Configuración centralizada y clientes AWS."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    tabla_eventos: str
    tabla_inscripciones: str
    correo_remitente: str
    aws_region: str


def get_settings() -> Settings:
    return Settings(
        tabla_eventos=os.getenv("TABLA_EVENTOS", "Eventos"),
        tabla_inscripciones=os.getenv("TABLA_INSCRIPCIONES", "Inscripciones"),
        correo_remitente=os.getenv("CORREO_REMITENTE", "organizador@example.com"),
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
    )
