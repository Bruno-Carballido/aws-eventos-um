# Documento del proyecto sobre el sistema de inscripción y recordatorios para eventos

## 1. Objetivo

Construir en AWS un sistema de inscripción y recordatorios para eventos. El usuario consulta una lista de eventos desde una página web estática, se inscribe, recibe una confirmación por correo electrónico y un recordatorio automático antes de que el evento ocurra. El backend corre sobre Amazon ECS con AWS Fargate y FastAPI, dentro de una VPC propia, y se balancea mediante un Application Load Balancer (ALB).

## 2. Alcance

1. Sitio web estático que lista los eventos disponibles (con cupos) y permite inscribirse.
2. API pública en FastAPI sobre ECS Fargate para consultar eventos, registrar inscripciones y consultar las inscripciones de un email (mis inscripciones).
3. Confirmación por correo electrónico ante cada inscripción vía Amazon SNS.
4. Recordatorio por correo antes de cada evento, enviado automáticamente por un planificador integrado en cada tarea de ECS.
5. Control de cupos por evento. Al llenarse, la inscripción se rechaza mediante incremento atómico condicional.
6. Persistencia de eventos e inscripciones en DynamoDB (tablas NoSQL on-demand).
7. Monitoreo de registros y errores en Amazon CloudWatch Logs.

Quedan fuera de alcance para esta entrega la autenticación de usuarios, los pagos, la cancelación de inscripciones y el multi-tenant.

## 3. Arquitectura

El flujo de datos es el siguiente:

1. El usuario abre la página estática alojada en Amazon S3, que lista los eventos consultando la API.
2. La página invoca `GET /eventos` a través del Application Load Balancer (ALB). El servicio ECS Fargate, que corre FastAPI, lee la tabla `Eventos` de DynamoDB y devuelve la lista ordenada por fecha con los cupos disponibles.
3. El usuario envía el formulario, y la página invoca `POST /inscripciones`. El backend en ECS valida que el evento exista y no haya ocurrido, evita duplicados (mismo email en el mismo evento), controla el cupo con un incremento condicional atómico sobre el contador `inscritos` (responde 409 si el evento se llenó) y registra la inscripción en la tabla `Inscripciones`.
4. La página permite buscar las inscripciones de un email mediante `GET /inscripciones?email=`. FastAPI consulta el GSI `porEmail` de la tabla `Inscripciones` y devuelve el historial del usuario.
5. Como parte del mismo proceso, el backend crea (o reutiliza) un topic de Amazon SNS por evento, suscribe el email del inscripto y publica el mensaje de confirmación. Solo los inscriptos de ese evento reciben sus correos.
6. Un planificador (`APScheduler`), integrado en el ciclo de vida de FastAPI, se ejecuta cada hora dentro de cada tarea de Fargate. Identifica los eventos que ocurren en las próximas 24 horas y publica un recordatorio en el topic SNS de cada evento. Un reclamo condicional sobre el campo `notificado` del evento garantiza que cada recordatorio se envía una sola vez, aunque haya varias tareas.
7. Amazon CloudWatch Logs centraliza los registros de las tareas (`/ecs/aws-eventos-um-backend`).

Las tareas de ECS están en subredes privadas de una VPC propia (`10.20.0.0/16`), sin ruta a Internet y sin NAT. Se comunican con DynamoDB, SNS, ECR y CloudWatch Logs por endpoints de VPC. El ALB está en subredes públicas, en dos zonas de disponibilidad.

### Diagrama de arquitectura

```
Navegador ──► S3 (sitio estático, HTTP)
     │
     │ GET /eventos, POST /inscripciones (puerto 80)
     ▼
Application Load Balancer (subredes públicas, dos zonas)
     │
     │ HTTP (puerto 8000)
     ▼
ECS Fargate, FastAPI (subredes privadas, de 1 a 3 tareas)
     │
     │ endpoints de VPC (sin NAT)
     ├──► DynamoDB (Eventos, Inscripciones)
     ├──► SNS (un topic por evento) ──► email
     ├──► ECR (imagen del backend)
     └──► CloudWatch Logs (/ecs/aws-eventos-um-backend)
```

## 4. Servicios de AWS

| Servicio | Rol en el proyecto |
|---|---|
| S3 | Aloja el sitio web estático (HTML/JS) con política de lectura pública. |
| Application Load Balancer (ALB) | Punto de entrada público en el puerto 80 que reparte el tráfico entre las tareas de Fargate, en dos zonas. |
| Amazon ECS (AWS Fargate) | Ejecución de contenedores para la API FastAPI. Cada tarea corre además el planificador horario de recordatorios. Escala de 1 a 3 tareas según el CPU. |
| Application Auto Scaling | Ajusta la cantidad de tareas entre 1 y 3, con objetivo de CPU promedio del 60 %. |
| Amazon VPC | Red propia (`10.20.0.0/16`) con subredes públicas para el ALB, subredes privadas para las tareas y endpoints de VPC. Sin NAT. |
| Amazon ECR | Registro administrado para la imagen Docker del backend (`aws-eventos-um-backend`). |
| DynamoDB | Tablas `Eventos` e `Inscripciones` (GSI por evento y por email), modo pago por petición. |
| SNS | Confirmación y recordatorios por email; un topic por evento. |
| CloudWatch Logs | Registro centralizado de eventos y errores de las tareas. |
| IAM | Permisos de ejecución de ECS y acceso a datos (`LabRole` en Academy, roles de mínimo privilegio en producción). |

### Nota sobre el entorno de despliegue y roles IAM

En AWS Academy Learner Lab no es posible crear roles de IAM propios (`iam:CreateRole` denegado). Por esta razón, el rol de ejecución y el rol de la tarea de ECS apuntan ambos a `LabRole`. En un entorno productivo real, se separan en roles de mínimo privilegio:

- El rol `ecsTaskExecutionRole` tiene permisos exclusivos de infraestructura, para descargar la imagen de ECR y crear logs en CloudWatch.
- El rol `backendEventosTaskRole` tiene permisos exclusivos de aplicación sobre DynamoDB (`Eventos`, `Inscripciones`) y SNS.

## 5. Algoritmos clave

1. Deduplicación de inscripciones. Antes de insertar, se consulta el GSI `porEvento` filtrando por email. Si ya existe, se responde 409. Complejidad O(1) sobre el índice.
2. Cupo atómico. El contador `inscritos` se incrementa con una condición atómica en DynamoDB (`attribute_not_exists(inscritos) OR inscritos < cupo`). Si la condición falla, se responde 409 sin insertar. Garantiza consistencia estricta ante concurrencia, también entre tareas.
3. Anti-repetición de recordatorios. Cada tarea hace un reclamo condicional sobre el evento antes de enviar el recordatorio. Solo una tarea gana el reclamo y publica. Si la publicación falla, la marca se libera y la siguiente ejecución horaria lo reintenta.

## 6. Entregables

1. Documento del proyecto (este archivo).
2. Plantilla CloudFormation desplegable (`template.yaml`).
3. Código fuente del backend en contenedor (`src/app/`, `Dockerfile`, `requirements.txt`).
4. Scripts de apoyo para ECR y datos (`scripts/build_and_push.*`, `scripts/seed_eventos.py`).
5. Sitio web estático (`web/`, compilado con Vite a `web/dist/`).
6. Informe técnico detallado de arquitectura, seguridad y roles IAM (`docs/Informe.md`).
