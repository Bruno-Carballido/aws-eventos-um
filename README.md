# Sistema de Inscripción y Recordatorios para Eventos (aws-eventos-um)

Proyecto de la materia AWS (UM). Permite consultar eventos, inscribirse y recibir
una confirmación por correo, más un recordatorio automático antes de cada evento.

## Arquitectura

```
Navegador ── S3 (sitio estático index.html, website endpoint HTTP)
     │ API HTTP
     ▼
API Gateway ──► Lambda ListarEventos ──► DynamoDB (Eventos)
     │
     └──► Lambda Inscribir ──► DynamoDB (Inscripciones)
                    │  SNS: un topic por evento → email de confirmación
EventBridge (cada 1 h) ──► Lambda Recordatorio ──► SNS → recordatorio
Cada Lambda loguea en CloudWatch Logs.
```

- **S3**: aloja el sitio estático con website endpoint (HTTP). CloudFront no está
  permitido en AWS Academy (`cloudfront:CreateOriginAccessControl` denegado), así que
  el sitio no tiene HTTPS propio; la API sí va por HTTPS.
- **API Gateway (HTTP API)**: expone `GET /eventos`, `POST /inscripciones` y
  `GET /inscripciones?email=` (mis inscripciones), con CORS habilitado.
- **Lambda** (Python 3.12): cuatro funciones — listar eventos, inscribir,
  mis inscripciones y recordatorio.
- **DynamoDB**: tabla `Eventos` e `Inscripciones` (GSI `porEvento` y `porEmail`),
  modo pago por petición. Los eventos llevan `cupo` e `inscritos` (contador
  atómico que bloquea la inscripción cuando se llena).
- **SNS**: un topic por evento; los inscriptos se suscriben con su email.
- **EventBridge** (regla programada): dispara el recordatorio cada 1 hora; solo notifica
  eventos dentro de las próximas 24 h y marca `notificado` para no repetir.
- **SQS (DLQ)**: cola muerta `recordatorio-dlq` para los eventos programados que
  fallen tras 2 reintentos; permite investigar fallos sin perder el evento.
- **CloudWatch**: logs y errores de las tres funciones.

## Despliegue (AWS Academy Learner Lab)

```bash
sam build
sam deploy --stack-name aws-eventos-um --region us-east-1 --resolve-s3 \n  --capabilities CAPABILITY_IAM \n  --parameter-overrides RolEjecucion=arn:aws:iam::<cuenta>:role/LabRole
sam list endpoints -o
```

Luego:

```bash
# 1. Cargar eventos de prueba
python scripts/seed_eventos.py --tabla Eventos

# 2. Construir el sitio (Vite + React)
cd web && npm install && npm run build && cd ..

# 3. Pegar el Output ApiUrl del stack en web/src/config.js (API_URL) y repetir el build

# 4. Publicar el sitio en el bucket (el nombre sale del Output BucketSitioWeb)
aws s3 sync web/dist/ s3://<bucket-del-sitio>/ --delete
```

La URL del sitio es el Output `UrlSitioWeb` (HTTPS). La distribución tarda unos
minutos en propagarse tras el primer deploy.

> En Academy toda Lambda reutiliza el `LabRole` preexistente; no se crean roles
> propios (restricción de IAM del laboratorio). El template ya queda así.

## Estructura

```
template.yaml            # stack SAM
src/listar_eventos/      # GET /eventos
src/inscribir/           # POST /inscripciones (valida, deduplica, controla cupo, confirma por email)
src/mis_inscripciones/   # GET /inscripciones?email= (mis inscripciones)
src/recordatorio/        # programada por EventBridge, envía recordatorios
web/                     # sitio Vite + React (npm run build genera web/dist/)
tests/                   # tests unitarios (python -m unittest discover tests)
scripts/seed_eventos.py
```

## Notas de diseño (arquitectura orientada a eventos)

- La inscripción se modela como un *domain event* (`InscripcionCreada`): la API
  responde apenas se registra, y la confirmación se procesa de forma asíncrona
  vía SNS — desacoplando el flujo de la respuesta HTTP.
- **Limitación**: SNS solo entrega a suscripciones confirmadas. El correo de
  confirmación de inscripción se publica en el momento de inscribirse, así que quien
  todavía no confirmó la suscripción no lo recibe. Lo primero que llega es el correo
  de confirmación de SNS, cuyo texto no es personalizable.
- **Idempotencia**: dedup por email+evento en la inscripción y atributo
  `notificado` en el evento para que un recordatorio no se envíe dos veces,
  aunque la Lambda programada se ejecute repetidamente.
- **Cupos**: el contador `inscritos` se incrementa con una condición atómica
  (`inscritos < cupo`), de modo que dos inscripciones simultáneas no pueden
  vender el último lugar dos veces; al llenarse, la API responde 409.
- **Resiliencia**: el evento programado que falle tras 2 reintentos cae a la
  DLQ (`recordatorio-dlq`, retención 14 días), desde donde puede re-procesarse.
- **Lambda fuera de VPC**: las funciones solo acceden a servicios públicos
  (DynamoDB, SNS, SQS), por lo que no se las conecta a una VPC — menos
  complejidad, sin ENIs ni NAT, y menor latencia (concepto de la clase de
  arquitecturas orientadas a eventos).
- Confirmación y recordatorios comparten el topic del evento, así solo los
  inscriptos de ese evento reciben correos.
- La suscripción SNS por email requiere un clic de confirmación del usuario
  (correo estándar de SNS).
- Anti-repetición de recordatorios: atributo `notificado` en el ítem del evento.
- Limitación conocida: `GET /inscripciones?email=` es público (sin
  autenticación) — cualquiera puede consultar inscripciones conociendo el
  email. Aceptable para la demo; se documenta en el informe de seguridad.
