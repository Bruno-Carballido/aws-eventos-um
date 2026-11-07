"""Punto de entrada principal de la aplicación FastAPI."""
import logging
from contextlib import asynccontextmanager

import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.config import get_settings
from src.app.routers import eventos, health, inscripciones
from src.app.scheduler import crear_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización de recursos AWS
    settings = get_settings()
    logger.info("Iniciando aplicación con tablas: Eventos=%s, Inscripciones=%s, Región=%s",
                settings.tabla_eventos, settings.tabla_inscripciones, settings.aws_region)

    if not hasattr(app.state, "dynamodb"):
        app.state.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    if not hasattr(app.state, "sns_client"):
        app.state.sns_client = boto3.client("sns", region_name=settings.aws_region)

    if not hasattr(app.state, "tabla_eventos"):
        app.state.tabla_eventos = app.state.dynamodb.Table(settings.tabla_eventos)
    if not hasattr(app.state, "tabla_inscripciones"):
        app.state.tabla_inscripciones = app.state.dynamodb.Table(settings.tabla_inscripciones)

    # Iniciar el planificador horario de recordatorios
    scheduler = crear_scheduler(app.state.tabla_eventos, app.state.sns_client)
    app.state.scheduler = scheduler
    scheduler.start()
    logger.info("Planificador en segundo plano iniciado (recordatorios cada 1 h).")

    yield

    # Apagado ordenado
    if hasattr(app.state, "scheduler") and app.state.scheduler.running:
        app.state.scheduler.shutdown()
        logger.info("Planificador en segundo plano detenido.")


app = FastAPI(
    title="Sistema de Inscripción a Eventos (UM)",
    description="API REST sobre Amazon ECS Fargate",
    version="1.0.0",
    lifespan=lifespan,
)

# Configuración de CORS idéntica a la que tenía API Gateway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Registro de routers
app.include_router(health.router)
app.include_router(eventos.router)
app.include_router(inscripciones.router)
