"""Tests de los correos (SNS): fecha legible en hora de Montevideo y texto cuidado."""
import os
import unittest
from unittest.mock import MagicMock

from tests._stubs import cargar_app

os.environ.setdefault("TABLA_EVENTOS", "Eventos")
os.environ.setdefault("TABLA_INSCRIPCIONES", "Inscripciones")


class TestFechaLegible(unittest.TestCase):
    def test_formato_en_hora_de_montevideo(self):
        app = cargar_app("inscribir")
        # 18:00 UTC = 15:00 en Montevideo (UTC-3, sin horario de verano)
        self.assertEqual(
            app.fecha_legible("2026-11-09T18:00:00Z"),
            "lunes 9 de noviembre de 2026, 15:00 h",
        )


class TestMensajeConfirmacion(unittest.TestCase):
    def test_correo_de_confirmacion_es_legible(self):
        app = cargar_app("inscribir")
        app.sns = MagicMock()
        app.sns.list_topics.return_value = {"Topics": []}
        app.sns.create_topic.return_value = {"TopicArn": "arn:evento-e-001"}

        app._confirmar_por_email(
            "e-001", "Charla de AWS", "ana@test.com", "Ana",
            "2026-11-09T18:00:00Z", "Aula 101",
        )

        publish = app.sns.publish.call_args.kwargs
        self.assertIn("Charla de AWS", publish["Subject"])
        self.assertIn("Hola Ana,", publish["Message"])
        self.assertIn("lunes 9 de noviembre de 2026, 15:00 h", publish["Message"])
        self.assertIn("Aula 101", publish["Message"])
        self.assertNotIn("2026-11-09T18:00:00Z", publish["Message"])


class TestMensajeRecordatorio(unittest.TestCase):
    def test_recordatorio_usa_fecha_legible(self):
        app = cargar_app("recordatorio")
        texto, asunto = app.construir_recordatorio(
            "Charla de AWS", "2026-11-09T18:00:00Z", "Aula 101")

        self.assertIn("Charla de AWS", asunto)
        self.assertIn("lunes 9 de noviembre de 2026, 15:00 h", texto)
        self.assertIn("Aula 101", texto)
        self.assertNotIn("T18:00:00Z", texto)


if __name__ == "__main__":
    unittest.main()
