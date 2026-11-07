"""Pruebas de integración de la API FastAPI usando TestClient."""
import unittest
from unittest.mock import MagicMock

from tests._stubs import install_boto_stubs

install_boto_stubs()

try:
    from fastapi.testclient import TestClient
    from src.app.main import app
    FASTAPI_DISPONIBLE = True
except ImportError:
    FASTAPI_DISPONIBLE = False


class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        if not FASTAPI_DISPONIBLE:
            self.skipTest("fastapi no está instalado en este entorno de testing local")

        self.tabla_eventos = MagicMock()
        self.tabla_inscr = MagicMock()
        self.sns = MagicMock()

        # Inyectar recursos mockeados en el estado de la app
        app.state.tabla_eventos = self.tabla_eventos
        app.state.tabla_inscripciones = self.tabla_inscr
        app.state.sns_client = self.sns

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health_check_devuelve_200(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_get_eventos_devuelve_lista(self):
        self.tabla_eventos.scan.return_value = {
            "Items": [
                {
                    "eventoId": "e-1",
                    "titulo": "Seminario Cloud",
                    "fecha": "2099-10-10T10:00:00Z",
                    "cupo": 50,
                    "inscritos": 10,
                }
            ]
        }
        response = self.client.get("/eventos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["titulo"], "Seminario Cloud")

    def test_post_inscripcion_faltan_campos_400(self):
        response = self.client.post("/inscripciones", json={"eventoId": "e-1"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_get_inscripciones_sin_email_400(self):
        response = self.client.get("/inscripciones")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_get_inscripciones_con_email_ok(self):
        self.tabla_inscr.query.return_value = {
            "Items": [
                {"inscripcionId": "i-1", "email": "test@um.edu.uy", "tituloEvento": "Seminario", "creadoEn": "2026-11-01T10:00:00Z"}
            ]
        }
        response = self.client.get("/inscripciones?email=test@um.edu.uy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)


if __name__ == "__main__":
    unittest.main()
