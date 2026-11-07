# Documento del proyecto — Sistema de inscripción y recordatorios para eventos

## 1. Objetivo

Construir en AWS un sistema de inscripción y recordatorios para eventos. El
usuario consulta una lista de eventos desde una página web estática, se
inscribe, recibe una confirmación por correo electrónico y un recordatorio
automático antes de que el evento ocurra. El proyecto implementa el ciclo
completo: exposición de API, procesamiento, persistencia, notificación
programada y monitoreo.

## 2. Alcance

1. Sitio web estático que lista los eventos disponibles (con cupos) y permite
   inscribirse.
2. API pública para consultar eventos, registrar inscripciones y consultar las
   inscripciones de un email (mis inscripciones).
3. Confirmación por correo electrónico ante cada inscripción.
4. Recordatorio por correo antes de cada evento, enviado automáticamente.
5. Control de cupos por evento: al llenarse, la inscripción se rechaza.
6. Persistencia de eventos e inscripciones en una base de datos NoSQL.
7. Monitoreo de registros y errores de todos los componentes.

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
   evento), controla el cupo con un incremento condicional atómico sobre el
   contador `inscritos` (responde 409 si el evento se llenó) y registra la
   inscripción en la tabla `Inscripciones`.
4. **Mis inscripciones.** La página permite buscar las inscripciones de un
   email mediante `GET /inscripciones?email=`; la función Lambda
   `MisInscripciones` consulta el GSI `porEmail` de la tabla `Inscripciones` y
   devuelve el historial del usuario.
5. **Confirmación.** Como parte del mismo proceso, la Lambda crea (o reutiliza)
   un topic de Amazon SNS por evento, suscribe el email del inscripto y publica
   el mensaje de confirmación. Solo los inscriptos de ese evento reciben sus
   correos. La inscripción se modela así como un *domain event*
   (`InscripcionCreada`) de procesamiento asíncrono, tal como se vio en la
   unidad de arquitecturas orientadas a eventos.
6. **Recordatorio.** Amazon EventBridge Scheduler dispara la función Lambda
   `Recordatorio` cada hora. Esta identifica los eventos que ocurren en las
   próximas 24 horas y publica un recordatorio en el topic SNS de cada evento.
   Un atributo `notificado` en el ítem del evento garantiza que cada
   recordatorio se envíe una sola vez (idempotencia).
7. **Resiliencia.** Si la ejecución programada falla tras 2 reintentos, el
   evento cae a una cola muerta (DLQ) de Amazon SQS con retención de 14 días,
   desde donde puede investigarse y re-procesarse sin pérdida.
8. **Monitoreo.** Amazon CloudWatch registra los logs y errores de las tres
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
| API Gateway (HTTP API) | Expone `GET /eventos`, `POST /inscripciones` y `GET /inscripciones?email=` con CORS habilitado. |
| Lambda | Cuatro funciones (Python): listar eventos, inscribir, mis inscripciones, recordatorio. |
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

### Red e interconexión de servicios

El sistema se compone de 6 canales de interconexión, todos sobre la red
gestionada de AWS salvo el acceso de los usuarios:

| # | De → A | Canal | Control de acceso |
|---|---|---|---|
| 1 | Navegador → CloudFront → S3 (sitio) | HTTPS en CloudFront; origen S3 privado | Origin Access Control: el bucket solo acepta lecturas de la distribución (`s3:GetObject` condicionado a `AWS:SourceArn`) |
| 2 | Navegador → API Gateway | HTTPS (edge global de AWS) | API abierta (demo) + CORS |
| 3 | API Gateway → Lambda | Invocación privada dentro de la red de AWS | Resource-based policy de la función |
| 4 | Lambda → DynamoDB / SNS / SQS | Endpoints de AWS por HTTPS | IAM mínimo privilegio por función |
| 5 | EventBridge Scheduler → Lambda | Invocación privada; DLQ a SQS | Resource-based policy + IAM |
| 6 | SNS → correo de usuarios | Salida SMTP hacia Internet | Suscripciones confirmadas por el usuario |

**Las funciones corren fuera de VPC, y es una decisión de arquitectura.** Según
el criterio visto en clase, una Lambda solo se conecta a una VPC cuando debe
acceder a recursos privados (RDS, ElastiCache, ALB internos) o forzar salida
privada mediante VPC endpoints. Todos los servicios de este proyecto
(DynamoDB, SNS, SQS, EventBridge) son públicos por diseño, así que las
funciones se ejecutan en la VPC administrada de AWS: sin ENIs, sin subnets ni
security groups que administrar, sin NAT Gateway ni endpoints, y sin el
impacto de cold start asociado a la configuración de red.

**La segmentación se logra con IAM.** En ausencia de security groups y NACLs,
el control de acceso de este diseño es la política de mínimo privilegio de
cada función: `ListarEventos` solo lee la tabla `Eventos`; `Inscribir` solo
accede a ambas tablas y publica en SNS; `MisInscripciones` solo lee
`Inscripciones`; `Recordatorio` lee `Eventos`, solo marca el flag de
notificación (`UpdateItem`), publica en SNS y envía a la DLQ. Es el
equivalente serverless de la microsegmentación de red.

**Si el sistema se desplegara dentro de una VPC** (alternativa analizada):
subnets privadas, **Gateway Endpoint** para DynamoDB y S3 (sin costo por
hora; el tráfico no sale a Internet) o **Interface Endpoints** para SNS/SQS
(cobran por hora y por ENI), y NAT Gateway solo si hiciera falta salir a
Internet. El trade-off es mayor complejidad operativa, ENIs y latencia
adicional, sin beneficio para este alcance.

**Sitio estático con HTTPS**: el website endpoint de S3 solo sirve HTTP y no
admite OAC, por lo que el bucket es privado y el sitio se publica a través de
**CloudFront** (origen REST de S3 + OAC + redirección a HTTPS). Así el sitio
y la API quedan ambos sobre HTTPS, y el bucket no expone objetos a Internet.

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
- **Bucket del sitio**: privado (bloqueo total de acceso público); solo la
  distribución de CloudFront puede leer objetos, por OAC.
- **No exponer datos de terceros**: la API no devuelve listados de emails de
  inscriptos; solo confirma la propia inscripción. Limitación aceptada y
  documentada: `GET /inscripciones?email=` es público (sin autenticación),
  por lo que quien conoce un email puede consultar sus inscripciones; fuera
  del alcance de la demo, se resolvería con autenticación (p. ej. Cognito).
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

> El procesamiento de datos no es el foco de la materia; se destacan tres
> rutinas cortas y demoables.

1. **Deduplicación de inscripciones.** Antes de insertar, se consulta el GSI
   `porEvento` filtrando por email: si ya existe, se responde 409. Complejidad
   O(1) sobre el índice; evita que un mismo usuario ocupe dos cupos.
2. **Cupo atómico.** El contador `inscritos` se incrementa con una condición
   (`attribute_not_exists(inscritos) OR inscritos < cupo`) en una sola
   operación de DynamoDB: si la condición falla, se responde 409 sin insertar.
   Es la barrera contra sobreventa ante inscripciones simultáneas.
3. **Anti-repetición de recordatorios.** El recordatorio marca cada evento con
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
3. Construir el sitio (`cd web && npm run build`), apuntar `web/src/config.js`
   a la URL de la API y publicar `web/dist/` en el bucket S3.
4. Inscribirse desde la página: verificar la inscripción en DynamoDB, el email
   de confirmación de SNS (con su clic de confirmación de suscripción) y el
   contador de cupos del evento incrementándose en la lista.
5. Llenar un evento (o bajar su cupo) y verificar que la página muestra
   "Sin lugares disponibles" y la API responde 409.
6. Buscar las inscripciones del email en la sección "Mis inscripciones".
7. Forzar la ejecución del recordatorio (invocar la Lambda con `sam local invoke`
   o esperar la ejecución horaria) y verificar el email del recordatorio.
8. Revisar los logs en CloudWatch y el estado de la DLQ.

## 11. Repositorio

Código fuente completo: https://github.com/Bruno-Carballido/aws-eventos-um

## Sources

[1] https://aws.amazon.com/lambda/pricing — AWS Lambda Pricing
[2] https://aws.amazon.com/dynamodb/pricing — Amazon DynamoDB Pricing
[3] https://aws.amazon.com/sns/pricing — Amazon SNS Pricing
