"""Router para health checks del Application Load Balancer (ALB)."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """Responde 200 OK para verificar que el contenedor y el proceso están activos."""
    return {"status": "ok"}
