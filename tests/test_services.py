"""Pruebas unitarias para los servicios del backend (Eventos, Inscripciones, Recordatorio)."""
import os
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from tests._stubs import error_condicional, install_boto_stubs

install_boto_stubs()


class TestEventosService(unittest.TestCase):
    def test_listar_eventos_convierte_decimal_y_ordena(self):
        from src.app.services.eventos_service import listar_eventos

        tabla = MagicMock()
        tabla.scan.return_value = {
            "Items": [
                {
                    "eventoId": "e-2",
                    "titulo": "Evento B",
                    "fecha": "2099-05-01T10:00:00Z",
                    "cupo": Decimal("50"),
                    "inscritos": Decimal("5"),
                },
                {
                    "eventoId": "e-1",
                    "titulo": "Evento A",
                    "fecha": "2099-01-01T10:00:00Z",
                    "cupo": Decimal("20"),
                    "inscritos": Decimal("10"),
                },
            ]
        }

        eventos = listar_eventos(tabla)

        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[0]["eventoId"], "e-1")
        self.assertEqual(eventos[0]["cupo"], 20)
        self.assertEqual(type(eventos[0]["cupo"]), int)
        self.assertEqual(eventos[1]["eventoId"], "e-2")
        self.assertEqual(eventos[1]["inscritos"], 5)
        self.assertEqual(type(eventos[1]["inscritos"]), int)

    def test_listar_eventos_sin_inscritos_devuelve_cero(self):
        from src.app.services.eventos_service import listar_eventos

        tabla = MagicMock()
        tabla.scan.return_value = {
            "Items": [{"eventoId": "e-9", "titulo": "Nuevo", "fecha": "2099-01-01T10:00:00Z", "cupo": Decimal("30")}]
        }

        eventos = listar_eventos(tabla)

        self.assertEqual(eventos[0]["inscritos"], 0)
        self.assertEqual(eventos[0]["cupo"], 30)


class TestInscripcionesService(unittest.TestCase):
    def setUp(self):
        self.tabla_eventos = MagicMock()
        self.tabla_inscr = MagicMock()
        self.sns = MagicMock()
        self.sns.list_topics.return_value = {"Topics": []}
        self.sns.create_topic.return_value = {"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-1"}

    def test_inscribir_exitoso(self):
        from src.app.services.inscripciones_service import inscribir_usuario

        self.tabla_eventos.get_item.return_value = {
            "Item": {
                "eventoId": "e-1",
                "titulo": "Charla AWS",
                "fecha": "2099-12-01T18:00:00Z",
                "lugar": "Aula Magna",
                "cupo": 30,
            }
        }
        self.tabla_inscr.query.return_value = {"Items": []}

        status, body = inscribir_usuario(
            {"eventoId": "e-1", "nombre": "Bruno", "email": "bruno@um.edu.uy"},
            self.tabla_eventos,
            self.tabla_inscr,
            self.sns,
        )

        self.assertEqual(status, 201)
        self.assertEqual(body["estado"], "confirmacion_enviada")
        self.assertIn("inscripcionId", body)
        self.tabla_inscr.put_item.assert_called_once()
        self.sns.publish.assert_called_once()

    def test_inscribir_evento_inexistente_404(self):
        from src.app.services.inscripciones_service import inscribir_usuario

        self.tabla_eventos.get_item.return_value = {"Item": None}

        status, body = inscribir_usuario(
            {"eventoId": "e-999", "nombre": "Bruno", "email": "bruno@um.edu.uy"},
            self.tabla_eventos,
            self.tabla_inscr,
            self.sns,
        )

        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "evento inexistente")

    def test_inscribir_sin_cupo_409(self):
        from src.app.services.inscripciones_service import inscribir_usuario

        self.tabla_eventos.get_item.return_value = {
            "Item": {
                "eventoId": "e-1",
                "titulo": "Charla Llena",
                "fecha": "2099-12-01T18:00:00Z",
                "cupo": 10,
            }
        }
        self.tabla_inscr.query.return_value = {"Items": []}
        self.tabla_eventos.update_item.side_effect = error_condicional()

        status, body = inscribir_usuario(
            {"eventoId": "e-1", "nombre": "Bruno", "email": "bruno@um.edu.uy"},
            self.tabla_eventos,
            self.tabla_inscr,
            self.sns,
        )

        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "sin cupos disponibles")

    def test_obtener_mis_inscripciones_ok(self):
        from src.app.services.inscripciones_service import obtener_mis_inscripciones

        self.tabla_inscr.query.return_value = {
            "Items": [
                {"inscripcionId": "i-1", "email": "bruno@um.edu.uy", "tituloEvento": "Charla 1", "creadoEn": "2026-11-01T10:00:00Z"},
                {"inscripcionId": "i-2", "email": "bruno@um.edu.uy", "tituloEvento": "Charla 2", "creadoEn": "2026-11-02T10:00:00Z"},
            ]
        }

        status, items = obtener_mis_inscripciones("bruno@um.edu.uy", self.tabla_inscr)

        self.assertEqual(status, 200)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["inscripcionId"], "i-2")  # Ordenado por creadoEn desc


class TestRecordatorioService(unittest.TestCase):
    def test_procesar_recordatorios_ignora_notificado(self):
        from datetime import datetime, timezone
        from src.app.services.recordatorio_service import procesar_recordatorios

        tabla_eventos = MagicMock()
        sns = MagicMock()
        sns.list_topics.return_value = {
            "Topics": [{"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-1"}]
        }

        ahora_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tabla_eventos.scan.return_value = {
            "Items": [
                {
                    "eventoId": "e-1",
                    "titulo": "Evento Próximo Ya Notificado",
                    "fecha": ahora_iso,
                    "notificado": ahora_iso,
                }
            ]
        }

        enviados = procesar_recordatorios(tabla_eventos, sns)

        self.assertEqual(enviados, [])
        sns.publish.assert_not_called()
        tabla_eventos.update_item.assert_not_called()

    def _evento_proximo(self):
        from datetime import datetime, timedelta, timezone

        fecha = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"eventoId": "e-1", "titulo": "Charla", "fecha": fecha, "lugar": "Aula"}

    def test_reclamo_condicional_evita_duplicado_entre_tareas(self):
        from src.app.services.recordatorio_service import procesar_recordatorios

        tabla_eventos = MagicMock()
        sns = MagicMock()
        sns.list_topics.return_value = {"Topics": [{"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-1"}]}
        evento = self._evento_proximo()
        tabla_eventos.scan.return_value = {"Items": [evento]}
        # Otra tarea ya reclamó el evento: la condición falla y no se publica nada.
        tabla_eventos.update_item.side_effect = error_condicional()

        enviados = procesar_recordatorios(tabla_eventos, sns)

        self.assertEqual(enviados, [])
        sns.publish.assert_not_called()

    def test_si_falla_la_publicacion_libera_el_reclamo(self):
        from src.app.services.recordatorio_service import procesar_recordatorios

        tabla_eventos = MagicMock()
        sns = MagicMock()
        sns.list_topics.return_value = {"Topics": [{"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-1"}]}
        evento = self._evento_proximo()
        tabla_eventos.scan.return_value = {"Items": [evento]}
        sns.publish.side_effect = RuntimeError("SNS caído")

        with self.assertRaises(RuntimeError):
            procesar_recordatorios(tabla_eventos, sns)

        ultima = tabla_eventos.update_item.call_args_list[-1].kwargs
        self.assertEqual(ultima["UpdateExpression"], "REMOVE notificado")
        self.assertEqual(ultima["ExpressionAttributeValues"], {":f": evento["fecha"]})

    def test_reclama_antes_de_publicar(self):
        from src.app.services.recordatorio_service import procesar_recordatorios

        tabla_eventos = MagicMock()
        sns = MagicMock()
        sns.list_topics.return_value = {"Topics": [{"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-1"}]}
        tabla_eventos.scan.return_value = {"Items": [self._evento_proximo()]}
        orden = MagicMock()
        orden.attach_mock(tabla_eventos.update_item, "reclamo")
        orden.attach_mock(sns.publish, "publicar")

        enviados = procesar_recordatorios(tabla_eventos, sns)

        self.assertEqual(enviados, ["e-1"])
        nombres = [c[0] for c in orden.mock_calls]
        self.assertEqual(nombres, ["reclamo", "publicar"])

    def test_reclamo_pasa_condicion_valida_a_dynamodb(self):
        # Stubber valida los parámetros contra el modelo real de DynamoDB (MagicMock no lo hace).
        import boto3
        from botocore.stub import Stubber
        from src.app.services.recordatorio_service import procesar_recordatorios

        os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
        tabla = boto3.resource("dynamodb", region_name="us-east-1").Table("Eventos")
        evento = self._evento_proximo()
        stub = Stubber(tabla.meta.client)
        stub.add_response(
            "scan",
            {"Items": [{
                "eventoId": {"S": "e-1"},
                "titulo": {"S": "Charla"},
                "fecha": {"S": evento["fecha"]},
                "lugar": {"S": "Aula"},
            }]},
            {"TableName": "Eventos", "ProjectionExpression": "eventoId,titulo,fecha,lugar,notificado"},
        )
        stub.add_response(
            "update_item",
            {"Attributes": {}},
            {
                "TableName": "Eventos",
                "Key": {"eventoId": "e-1"},
                "UpdateExpression": "SET notificado = :f",
                "ConditionExpression": "attribute_not_exists(notificado) OR notificado <> :f",
                "ExpressionAttributeValues": {":f": evento["fecha"]},
            },
        )
        sns = MagicMock()
        sns.list_topics.return_value = {"Topics": [{"TopicArn": "arn:aws:sns:us-east-1:1:evento-e-1"}]}

        with stub:
            enviados = procesar_recordatorios(tabla, sns)
            stub.assert_no_pending_responses()

        self.assertEqual(enviados, ["e-1"])


if __name__ == "__main__":
    unittest.main()
