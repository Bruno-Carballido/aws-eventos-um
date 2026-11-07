"""Stubs de boto3/botocore para testear las lambdas sin dependencias."""
import importlib.util
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class ClientError(Exception):
    def __init__(self, error_response, operation_name):
        self.response = error_response
        self.operation_name = operation_name
        super().__init__(str(error_response))


def install_boto_stubs():
    try:
        import boto3  # noqa: F401
        import botocore.exceptions  # noqa: F401
        return  # librerías reales disponibles: no reemplazar
    except ImportError:
        pass
    if "boto3" not in sys.modules:
        boto3 = types.ModuleType("boto3")
        boto3.resource = lambda *a, **k: None
        boto3.client = lambda *a, **k: None
        sys.modules["boto3"] = boto3
    if "botocore" not in sys.modules:
        botocore = types.ModuleType("botocore")
        exceptions = types.ModuleType("botocore.exceptions")
        exceptions.ClientError = ClientError
        botocore.exceptions = exceptions
        sys.modules["botocore"] = botocore
        sys.modules["botocore.exceptions"] = exceptions


def cargar_app(nombre_carpeta):
    """Importa src/<nombre_carpeta>/app.py como modulo unico."""
    install_boto_stubs()
    ruta = RAIZ / "src" / nombre_carpeta / "app.py"
    nombre = f"app_{nombre_carpeta}"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def error_condicional():
    """ClientError con codigo ConditionalCheckFailedException (real o stub)."""
    try:
        from botocore.exceptions import ClientError as CE
    except ImportError:
        CE = ClientError
    return CE({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
