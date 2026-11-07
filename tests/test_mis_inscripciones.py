"""Tests del endpoint Mis Inscripciones (Task 2)."""
import json
import os
import unittest
from unittest.mock import MagicMock

from tests._stubs import cargar_app

os.environ.setdefault("TABLA_INSCRIPCIONES", "Inscripciones")


class TestMisInscripciones(unittest.TestCase):
    def _app(self, items):
        app = cargar_app("mis_inscripciones")
        tabla = MagicMock()
        tabla.query.return_value = {"Items": items}
        app.dynamodb = MagicMock()
        app.dynamodb.Table.return_value = tabla
        return app, tabla

    def test_consulta_por_email_devuelve_inscripciones(self):
        items = [{"inscripcionId": "i-1", "eventoId": "e-001",
                  "tituloEvento": "Charla", "email": "ana@test.com",
                  "creadoEn": "2026-11-01T10:00:00Z"}]
        app, tabla = self._app(items)

        resp = app.handler(
            {"queryStringParameters": {"email": "ana@test.com"}}, None)

        self.assertEqual(resp["statusCode"], 200)
        cuerpo = json.loads(resp["body"])
        self.assertEqual(cuerpo[0]["tituloEvento"], "Charla")
        kwargs = tabla.query.call_args.kwargs
        self.assertEqual(kwargs["IndexName"], "porEmail")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":m"], "ana@test.com")

    def test_email_faltante_devuelve_400(self):
        app, tabla = self._app([])

        resp = app.handler({}, None)

        self.assertEqual(resp["statusCode"], 400)
        tabla.query.assert_not_called()

    def test_email_normalizado(self):
        app, tabla = self._app([])

        app.handler({"queryStringParameters": {"email": "  A@B.com "}}, None)

        kwargs = tabla.query.call_args.kwargs
        self.assertEqual(kwargs["ExpressionAttributeValues"][":m"], "a@b.com")


if __name__ == "__main__":
    unittest.main()