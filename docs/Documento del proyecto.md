# Documento del proyecto — Sistema de inscripción y recordatorios para eventos

## 1. Objetivo

Construir en AWS un sistema de inscripción y recordatorios para eventos. El
usuario consulta una lista de eventos desde una página web estática, se
inscribe, recibe una confirmación por correo electrónico y un recordatorio
automático antes de que el evento ocurra. El proyecto implementa el ciclo
completo: exposición de API, procesamiento, persistencia, notificación
programada y monitoreo.

## 2. Alcance

1. Sitio web estático que lista los eventos disponibles y permite inscribirse.
2. API pública para consultar eventos y registrar inscripciones.
3. Confirmación por correo electrónico ante cada inscripción.
4. Recordatorio por correo antes de cada evento, enviado automáticamente.
5. Persistencia de eventos e inscripciones en una base de datos NoSQL.
6. Monitoreo de registros y errores de todos los componentes.

Fuera de alcance para esta entrega: autenticación de usuarios, pagos,
cancelación de inscripciones y multi-tenant.

## 3. Arquitectura

El flujo de datos es el siguiente:

1. **Acceso al sitio.** El usuario abre la página estática alojada en Amazon
   S3, que lista los eventos consultando la API.
2. **Consulta de eventos.** La página invoca `GET /eventos` en Amazon API
   Gateway; la función Lambda `ListarEventos` lee la tabla `Eventos` de
   DynamoDB y devuelve la lista ordenada por fecha.
3. **Inscripción.** El usuario envía el formulario; la página invoca
   `POST /inscripciones` y la función Lambda `Inscribir` valida que el evento
   exista y no haya ocurrido, evita duplicados (mismo email en el mismo
   evento) y registra la inscripción en la tabla `Inscripciones`.
4. **Confirmación.** Como parte del mismo proceso, la Lambda crea (o reutiliza)
   un topic de Amazon SNS por evento, suscribe el email del inscripto y publica
   el mensaje de confirmación. Solo los inscriptos de ese evento reciben sus
   correos. La inscripción se modela así como un *domain event*
   (`InscripcionCreada`) de procesamiento asíncrono, tal como se vio en la
   unidad de arquitecturas orientadas a eventos.
5. **Recordatorio.** Amazon EventBridge Scheduler dispara la función Lambda
   `Recordatorio` cada hora. Esta identifica los eventos que ocurren en las
   próximas 24 horas y publica un recordatorio en el topic SNS de cada evento.
   Un atributo `notificado` en el ítem del evento garantiza que cada
   recordatorio se envíe una sola vez (idempotencia).
6. **Resiliencia.** Si la ejecución programada falla tras 2 reintentos, el
   evento cae a una cola muerta (DLQ) de Amazon SQS con retención de 14 días,
   desde donde puede investigarse y re-procesarse sin pérdida.
7. **Monitoreo.** Amazon CloudWatch registra los logs y errores de las tres
   funciones Lambda, y expone las métricas de la API.

### Diagrama de arquitectura

```
                       ┌─────────────────────────────┐
   Navegador ─────────►│  S3 (sitio estático)        │
        │              └─────────────────────────────┘
        │ GET /eventos / POST /inscripciones
        ▼
┌────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ API Gateway    │──►│ Lambda           │──►│ DynamoDB         │
│ (HTTP API)     │   │ ListarEventos    │   │ Eventos          │
│                │   │ Inscribir        │   │ Inscripciones    │
└────────────────┘   └───────┬──────────┘   └──────────────────┘
                             │ SNS (topic por evento)
                             ▼
                     ┌──────────────────┐
                     │ SNS ──► email    │  confirmación
                     └──────────────────┘
┌──────────────────┐  cada 1 h  ┌──────────────────┐
│ EventBridge      │───────────►│ Lambda           │──► SNS (recordatorio)
│ Scheduler        │            │ Recordatorio     │──► DynamoDB (marca notificado)
└──────────────────┘            └────────┬─────────┘
        fallos tras reintentos ─────────► SQS (DLQ)

        CloudWatch: logs y errores de las tres funciones
```

> El diagrama formal (imagen) se entrega como entregable aparte.

## 4. Servicios de AWS

| Servicio | Rol en el proyecto |
|---|---|
| S3 | Aloja el sitio web estático (HTML/JS) con política de lectura pública. |
| API Gateway (HTTP API) | Expone `GET /eventos` y `POST /inscripciones` con CORS habilitado. |
| Lambda | Tres funciones (Python): listar eventos, inscribir, recordatorio. |
| DynamoDB | Tablas `Eventos` e `Inscripciones` (GSI por evento y por email), modo pago por petición. |
| SNS | Confirmación y recordatorios por email; un topic por evento. |
| EventBridge Scheduler | Dispara la función de recordatorio cada hora. |
| SQS | Cola muerta (DLQ) para los eventos programados que fallan tras reintentos. |
| CloudWatch | Logs, métricas y errores de las funciones y la API. |
| IAM | Permisos de mínimo privilegio de cada función (vía LabRole en Academy). |

### Nota sobre el entorno de despliegue

La demo se implementa en AWS Academy, cuyo IAM no permite crear roles propios:
todas las funciones reutilizan el `LabRole` preexistente, que es el equivalente
académico de un rol de ejecución por función con políticas de mínimo
privilegio. El resto de los servicios del diseño están disponibles en el
laboratorio tal cual, sin equivalencias necesarias.

## 5. Seguridad

- **Mínimo privilegio por diseño**: cada función declara solo los permisos que
  necesita (lectura de `Eventos`, CRUD de `Inscripciones`, publicación en SNS).
  En Academy se materializa sobre `LabRole` por restricción del laboratorio.
- **Validación de entrada**: la API rechaza peticiones con campos faltantes o
  inválidos (400), eventos inexistentes (404) y eventos ya ocurridos.
- **Sin credenciales en el código**: la configuración (tablas, remitente) viaja
  en variables de entorno de Lambda; las credenciales las provee el rol de
  ejecución vía IAM, nunca llaves embebidas.
- **HTTPS en la API**: API Gateway expone el endpoint solo por HTTPS.
- **Bucket del sitio**: política acotada a `s3:GetObject` sobre los objetos del
  sitio; el resto de las acciones de S3 quedan bloqueadas por defecto.
- **No exponer datos de terceros**: la API no devuelve listados de emails de
  inscriptos; solo confirma la propia inscripción.
- **DLQ y logs acotados**: los logs de CloudWatch no registran datos sensibles
  (solo IDs y estados); la DLQ permite auditar fallos sin dispersar eventos.

## 6. Escalabilidad

- **Serverless de extremo a extremo**: API Gateway, Lambda y DynamoDB ajustan
  capacidad automáticamente; no hay servidores que aprovisionar.
- **DynamoDB en modo pago por petición**: absorbe picos de inscripción (p. ej.,
  apertura de inscripciones a un evento popular) sin planificar capacidad.
- **Confirmación asíncrona**: el envío de correos no bloquea la respuesta HTTP;
  la API responde apenas se registra la inscripción.
- **Recordatorio por lotes horarios**: la ventana de 24 h distribuye la carga y
  evita un barrido costoso; el filtro `notificado` mantiene la operación
  idempotente ante ejecuciones repetidas.
- **Crecimiento de catálogo**: el scan acotado del catálogo de eventos alcanza
  para el alcance del proyecto; con catálogos grandes se reemplaza por un GSI
  de fecha, sin cambiar la arquitectura.
- **Lambdas fuera de VPC**: al no acceder a recursos privados, se ejecutan en la
  red administrada de AWS, sin ENIs ni NAT que limiten la concurrencia.

## 7. Algoritmos

> El procesamiento de datos no es el foco de la materia; se destacan dos
> rutinas cortas y demoables.

1. **Deduplicación de inscripciones.** Antes de insertar, se consulta el GSI
   `porEvento` filtrando por email: si ya existe, se responde 409. Complejidad
   O(1) sobre el índice; evita que un mismo usuario ocupe dos cupos.
2. **Anti-repetición de recordatorios.** El recordatorio marca cada evento con
   `notificado = fecha` del evento; la siguiente ejecución horaria salta los
   eventos ya marcados. Es la forma idempotente de operar un trigger periódico.

## 8. Costos

El presupuesto de AWS Academy es limitado; el diseño es de bajo consumo:

- **Lambda**: el free tier cubre un millón de solicitudes y 400.000 GB-segundos
  por mes[1]; el volumen de la demo (unas pocas ejecuciones por hora) queda muy
  por debajo.
- **DynamoDB**: en modo pago por petición se cobra por solicitud de lectura y
  escritura[2]; con dos tablas pequeñas y tráfico de demo, el costo es
  prácticamente nulo (cabe incluso el free tier permanente de DynamoDB).
- **SNS**: se cobra por solicitudes de API y por entrega de notificaciones[3];
  cada inscripción y cada recordatorio son un par de mensajes pequeños —
  centavos por mes con volúmenes de curso.
- **API Gateway y EventBridge Scheduler**: costo por millón de invocaciones y
  por invocación programada, despreciable en este volumen.
- **S3**: almacenamiento de un sitio estático (pocos KB) y transferencia de
  salida mínima.
- **Costos de error controlados**: la DLQ de SQS evita reintentos infinitos que
  consumirían invocaciones; el filtro `notificado` evita envíos duplicados.

Estimación global: **menos de USD 1/mes** para la carga de la demo, dentro de
los créditos del laboratorio.

## 9. Entregables

1. Documento del proyecto (este archivo).
2. Diagrama de arquitectura (imagen).
3. Template SAM/CloudFormation desplegable en Academy (`template.yaml`).
4. Scripts auxiliares (`scripts/seed_eventos.py`).
5. Sitio web estático (`web/index.html`).
6. Demo end-to-end: listado, inscripción, confirmación y recordatorio.

## 10. Demo

1. Desplegar el stack (`sam build && sam deploy --guided`).
2. Cargar eventos de prueba (`python scripts/seed_eventos.py`).
3. Publicar el sitio en el bucket S3 y apuntar `web/index.html` a la URL de la API.
4. Inscribirse desde la página: verificar la inscripción en DynamoDB y el email
   de confirmación de SNS (con su clic de confirmación de suscripción).
5. Forzar la ejecución del recordatorio (invocar la Lambda con `sam local invoke`
   o esperar la ejecución horaria) y verificar el email del recordatorio.
6. Revisar los logs en CloudWatch y el estado de la DLQ.

## 11. Repositorio

Código fuente completo: https://github.com/Bruno-Carballido/aws-eventos-um

## Sources

[1] https://aws.amazon.com/lambda/pricing — AWS Lambda Pricing
[2] https://aws.amazon.com/dynamodb/pricing — Amazon DynamoDB Pricing
[3] https://aws.amazon.com/sns/pricing — Amazon SNS Pricing
