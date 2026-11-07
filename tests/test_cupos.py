"""Tests del contador de cupos (Task 1)."""
import json
import os
import unittest
from unittest.mock import MagicMock

from tests._stubs import cargar_app, error_condicional

os.environ.setdefault("TABLA_EVENTOS", "Eventos")
os.environ.setdefault("TABLA_INSCRIPCIONES", "Inscripciones")


class TestListarCupos(unittest.TestCase):
    def test_listar_incluye_cupo_e_inscritos(self):
        app = cargar_app("listar_eventos")
        tabla = MagicMock()
        tabla.scan.return_value = {"Items": [
            {"eventoId": "e-001", "titulo": "Charla", "fecha": "2099-01-01T18:00:00Z",
             "cupo": 30, "inscritos": 12},
        ]}
        app.dynamodb = MagicMock()
        app.dynamodb.Table.return_value = tabla

        resp = app.handler({}, None)
        cuerpo = json.loads(resp["body"])

        self.assertEqual(cuerpo[0]["cupo"], 30)
        self.assertEqual(cuerpo[0]["inscritos"], 12)
        proyeccion = tabla.scan.call_args.kwargs.get("ProjectionExpression", "")
        self.assertIn("cupo", proyeccion)
        self.assertIn("inscritos", proyeccion)


class TestInscribirCupos(unittest.TestCase):
    def _app_con_tablas(self, evento):
        app = cargar_app("inscribir")
        tabla_eventos = MagicMock()
        tabla_eventos.get_item.return_value = {"Item": evento}
        tabla_inscr = MagicMock()
        tabla_inscr.query.return_value = {"Items": []}
        app.dynamodb = MagicMock()
        app.dynamodb.Table.side_effect = lambda nombre: (
            tabla_eventos if nombre == "Eventos" else tabla_inscr
        )
        app.sns = MagicMock()
        app.sns.list_topics.return_value = {"Topics": []}
        app.sns.create_topic.return_value = {"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-001"}
        return app, tabla_eventos, tabla_inscr

    def test_inscribir_ok_incremente_contador(self):
        evento = {"eventoId": "e-001", "titulo": "Charla",
                  "fecha": "2099-01-01T18:00:00Z", "cupo": 30}
        app, tabla_eventos, tabla_inscr = self._app_con_tablas(evento)

        resp = app.handler({"body": json.dumps(
            {"eventoId": "e-001", "nombre": "Ana", "email": "ana@test.com"})}, None)

        self.assertEqual(resp["statusCode"], 201)
        kwargs = tabla_eventos.update_item.call_args.kwargs
        self.assertIn("ADD inscritos", kwargs["UpdateExpression"])
        self.assertIn("inscritos < :cupo", kwargs["ConditionExpression"])
        self.assertEqual(kwargs["ExpressionAttributeValues"][":uno"], 1)
        self.assertEqual(kwargs["ExpressionAttributeValues"][":cupo"], 30)
        item = tabla_inscr.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["tituloEvento"], "Charla")

    def test_inscribir_sin_cupos_devuelve_409(self):
        evento = {"eventoId": "e-001", "titulo": "Charla",
                  "fecha": "2099-01-01T18:00:00Z", "cupo": 30}
        app, tabla_eventos, tabla_inscr = self._app_con_tablas(evento)
        tabla_eventos.update_item.side_effect = error_condicional()

        resp = app.handler({"body": json.dumps(
            {"eventoId": "e-001", "nombre": "Ana", "email": "ana@test.com"})}, None)

        self.assertEqual(resp["statusCode"], 409)
        self.assertEqual(json.loads(resp["body"])["error"], "sin cupos disponibles")
        tabla_inscr.put_item.assert_not_called()

    def test_evento_sin_atributo_inscritos_cuenta_como_cero(self):
        evento = {"eventoId": "e-001", "titulo": "Charla",
                  "fecha": "2099-01-01T18:00:00Z", "cupo": 30}
        app, tabla_eventos, _ = self._app_con_tablas(evento)

        app.handler({"body": json.dumps(
            {"eventoId": "e-001", "nombre": "Ana", "email": "ana@test.com"})}, None)

        condicion = tabla_eventos.update_item.call_args.kwargs["ConditionExpression"]
        self.assertIn("attribute_not_exists(inscritos)", condicion)

    def test_inscribir_normaliza_email(self):
        evento = {"eventoId": "e-001", "titulo": "Charla",
                  "fecha": "2099-01-01T18:00:00Z", "cupo": 30}
        app, _, tabla_inscr = self._app_con_tablas(evento)

        app.handler({"body": json.dumps(
            {"eventoId": "e-001", "nombre": "Ana", "email": "  A@B.com "})}, None)

        item = tabla_inscr.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["email"], "a@b.com")


if __name__ == "__main__":
    unittest.main()
