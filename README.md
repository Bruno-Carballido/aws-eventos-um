# Sistema de Inscripción y Recordatorios para Eventos (aws-eventos-um)

Proyecto de la materia AWS (UM). Permite consultar eventos, inscribirse y recibir
una confirmación por correo, más un recordatorio automático antes de cada evento.

## Arquitectura

```
Navegador ── S3 (sitio estático index.html)
     │ API HTTP
     ▼
API Gateway ──► Lambda ListarEventos ──► DynamoDB (Eventos)
     │
     └──► Lambda Inscribir ──► DynamoDB (Inscripciones)
                    │  SNS: un topic por evento → email de confirmación
EventBridge (cada 1 h) ──► Lambda Recordatorio ──► SNS → recordatorio
Cada Lambda loguea en CloudWatch Logs.
```

- **S3**: aloja la página estática (lista de eventos + formulario de inscripción).
- **API Gateway (HTTP API)**: expone `GET /eventos` y `POST /inscripciones` con CORS.
- **Lambda** (Python 3.12): tres funciones — listar, inscribir, recordatorio.
- **DynamoDB**: tabla `Eventos` y tabla `Inscripciones` (GSI `porEvento` y `porEmail`).
- **SNS**: un topic por evento; los inscriptos se suscriben con su email.
- **EventBridge Scheduler**: dispara el recordatorio cada 1 hora; solo notifica
  eventos dentro de las próximas 24 h y marca `notificado` para no repetir.
- **CloudWatch**: logs y errores de las tres funciones.

## Despliegue (AWS Academy Learner Lab)

```bash
sam build
sam deploy --guided   # aceptar el rol LabRole cuando SAM pregunte
sam list endpoints -o
```

Luego:

```bash
# 1. Cargar eventos de prueba
python scripts/seed_eventos.py --tabla Eventos

# 2. Publicar el sitio
aws s3 cp web/ s3://<bucket-del-sitio>/ --recursive

# 3. Pegar el Output ApiUrl del stack en web/index.html (const API) y re-subir
```

> En Academy toda Lambda reutiliza el `LabRole` preexistente; no se crean roles
> propios (restricción de IAM del laboratorio). El template ya queda así.

## Estructura

```
template.yaml          # stack SAM
src/listar_eventos/    # GET /eventos
src/inscribir/         # POST /inscripciones (valida, deduplica, confirma por email)
src/recordatorio/      # programada por EventBridge, envía recordatorios
web/index.html         # página estática
scripts/seed_eventos.py
```

## Notas de diseño

- Confirmación y recordatorios comparten el topic del evento, así solo los
  inscriptos de ese evento reciben correos.
- La suscripción SNS por email requiere un clic de confirmación del usuario
  (correo estándar de SNS).
- Anti-repetición de recordatorios: atributo `notificado` en el ítem del evento.
