"""Planificador en segundo plano para el envío periódico de recordatorios."""
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.app.services.recordatorio_service import procesar_recordatorios

logger = logging.getLogger("scheduler")


def crear_scheduler(tabla_eventos: Any, sns_client: Any) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    async def tarea_recordatorio():
        logger.info("Iniciando verificación horaria de recordatorios...")
        try:
            enviados = procesar_recordatorios(tabla_eventos, sns_client)
            logger.info("Recordatorios procesados exitosamente: %s enviados", len(enviados))
        except Exception as exc:
            logger.error("Error al procesar recordatorios periódicos: %s", exc, exc_info=True)

    # Programar cada 1 hora
    scheduler.add_job(
        tarea_recordatorio,
        "interval",
        hours=1,
        id="job_recordatorios_horario",
        replace_existing=True,
    )
    return scheduler
