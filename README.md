# Sistema de Inscripción y Recordatorios para Eventos (aws-eventos-um)

Proyecto de la materia AWS (UM). Permite consultar eventos, inscribirse y recibir
una confirmación por correo, más un recordatorio automático antes de cada evento.
El backend corre en Amazon ECS con AWS Fargate y FastAPI, detrás de un Application
Load Balancer (ALB), dentro de una VPC propia con subredes privadas y endpoints.

## Arquitectura

```
Navegador ──► S3 (sitio estático, website endpoint HTTP)
     │
     │ HTTP (puerto 80)
     ▼
Application Load Balancer (subredes públicas, dos zonas)
     │
     │ HTTP (puerto 8000)
     ▼
ECS Fargate (subredes privadas, dos zonas, 1 a 3 tareas)
     ├── Rutas: GET /eventos, POST /inscripciones, GET /inscripciones, GET /health
     └── Planificador (APScheduler): recordatorios cada 1 hora dentro de cada tarea
           │
           │ endpoints de VPC (sin NAT, sin salida a Internet)
           ├──► DynamoDB (Eventos, Inscripciones)
           ├──► SNS (un topic por evento: confirmación y recordatorio)
           ├──► CloudWatch Logs
           └──► ECR (descarga de la imagen)
```

- **VPC propia** (`10.20.0.0/16`): dos subredes públicas para el ALB y dos subredes privadas para las tareas. Las privadas no tienen ruta a Internet y no hay NAT.
- **Endpoints de VPC**: Gateway para S3 y DynamoDB; de interfaz para ECR (API y Docker), CloudWatch Logs y SNS.
- **Application Load Balancer**: público, puerto 80, con health check en `/health`.
- **ECS Fargate**: servicio con FastAPI y Uvicorn (0.25 vCPU y 0.5 GB de memoria). Escala de 1 a 3 tareas según el CPU promedio (objetivo 60 %).
- **Recordatorios**: `APScheduler` corre dentro de cada tarea cada hora. Un reclamo condicional por evento en DynamoDB evita enviar el mismo recordatorio dos veces aunque haya varias tareas.
- **DynamoDB**: tablas `Eventos` e `Inscripciones` (índices `porEvento` y `porEmail`), modo on-demand. Los cupos se controlan con un incremento condicional atómico (`inscritos < cupo`).
- **SNS**: un topic por evento. Cada inscripto confirma su suscripción por correo.
- **S3**: aloja el frontend compilado con React y Vite.
- **ECR**: repositorio `aws-eventos-um-backend` con escaneo al subir.
- **CloudWatch Logs**: grupo `/ecs/aws-eventos-um-backend`, retención de 7 días.

## Requisitos

- AWS CLI con el perfil de AWS Academy (`um`) y región `us-east-1`.
- Docker en ejecución. En WSL: `sudo apt install -y docker.io` y permiso para el usuario en el grupo `docker`.
- Python 3.12 o superior para las pruebas locales.
- Node 22 para compilar el sitio web.

## Pruebas

```bash
python -m pip install -r src/requirements.txt httpx
python -m unittest discover tests      # 29 pruebas
cfn-lint template.yaml
```

Las pruebas usan MagicMock para la lógica de negocio y `botocore.stub.Stubber` para validar los parámetros de DynamoDB contra el modelo real de AWS. `httpx` hace falta para las pruebas de la API.

## Despliegue (AWS Academy Learner Lab)

### 1. Crear el stack

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name aws-eventos-um \
  --region us-east-1 \
  --parameter-overrides \
      RolEjecucion=arn:aws:iam::<cuenta>:role/LabRole \
      ImagenBackend=<cuenta>.dkr.ecr.us-east-1.amazonaws.com/aws-eventos-um-backend:latest \
      CorreoRemitente=organizador@example.com
```

El template crea la VPC, las subredes, los endpoints, el ALB, el cluster ECS, el repositorio ECR, las tablas de DynamoDB y el bucket del sitio. No hace falta indicar VPC ni subredes.

La imagen todavía no existe cuando se crea el stack. Mientras no esté subida, la tarea falla con `CannotPullContainerError`. Es el comportamiento esperado: CloudFormation espera a que el servicio esté estable, así que el comando no termina hasta que una tarea arranca. Subí la imagen (paso 2) desde otra terminal cuando el repositorio ya exista, y ECS reintenta solo.

### 2. Compilar y subir la imagen a ECR

Requiere Docker en ejecución.

```bash
# En Linux, macOS o WSL:
bash scripts/build_and_push.sh

# En Windows (sin probar en esta sesión):
scripts\build_and_push.bat
```

El script imprime la URI completa de la imagen, que es el valor de `ImagenBackend`.

Si la tarea ya estaba fallando, forzar un nuevo despliegue para que tome la imagen:

```bash
aws ecs update-service --cluster aws-eventos-um-cluster --service servicio-eventos-backend --force-new-deployment
```

### 3. Cargar datos y publicar el sitio

```bash
# 1. Cargar eventos de prueba (desde la imagen, con las credenciales montadas en solo lectura)
docker run --rm \
  -v "$HOME/.aws:/root/.aws:ro" \
  -e AWS_PROFILE=um -e AWS_DEFAULT_REGION=us-east-1 \
  -v "$PWD/scripts:/scripts:ro" \
  aws-eventos-um-backend python /scripts/seed_eventos.py --tabla Eventos

# 2. Pegar la URL del balanceador (Output ApiUrl) en web/src/config.js (API_URL)

# 3. Compilar el sitio web
cd web && npm install && npm run build && cd ..

# 4. Publicar el sitio en el bucket S3 (Output BucketSitioWeb)
aws s3 sync web/dist/ s3://<bucket-del-sitio>/ --delete
```

La URL del sitio está en el Output `UrlSitioWeb`. El sitio usa HTTP.

### 4. Desmontar todo (para no dejar cobros activos)

El stack cobra por hora mientras existe: el ALB, la tarea mínima y los endpoints de interfaz. Para eliminarlo:

```bash
# 1. Vaciar el bucket del sitio (CloudFormation no lo borra si tiene objetos)
aws s3 rm s3://<bucket-del-sitio>/ --recursive

# 2. Borrar los topics SNS que creó la aplicación (no están en el stack)
aws sns list-topics --query "Topics[?contains(TopicArn, ':evento-')].TopicArn" --output text
aws sns delete-topic --topic-arn <arn-de-cada-topic>

# 3. Borrar el stack (incluye el repositorio ECR con sus imágenes, por EmptyOnDelete)
aws cloudformation delete-stack --stack-name aws-eventos-um
aws cloudformation wait stack-delete-complete --stack-name aws-eventos-um
```

Después, verificar que no quedó nada: `aws ec2 describe-vpcs` no debe mostrar la VPC `vpc-aws-eventos-um`, y `aws elbv2 describe-load-balancers` no debe mostrar `alb-eventos-um`.

## Escalado

- Mínimo 1 tarea, máximo 3, objetivo de CPU promedio 60 %.
- Escala hacia arriba con 60 segundos de enfriamiento y hacia abajo con 300 segundos.
- Para ver la actividad de escalado: `aws application-autoscaling describe-scaling-activities --service-namespace ecs --resource-id service/aws-eventos-um-cluster/servicio-eventos-backend`.

## Verificación realizada (2026-11-07, Academy us-east-1)

- Pruebas unitarias: 29 de 29. `cfn-lint` y `validate-template` sin errores.
- Contenedor local: `/health` 200, `/inscripciones` sin email 400.
- Stack en `CREATE_COMPLETE`. Destino del ALB `healthy` en una subred privada.
- API por el ALB: `/health` 200, `/eventos` 200, inscripción 201, duplicado 409, consulta por email 200, email inválido 400.
- Concurrencia: 12 inscripciones simultáneas a un evento de cupo 10 dieron 10 respuestas 201 y 2 respuestas 409.
- Recordatorios: dos ejecuciones simultáneas sobre el mismo evento enviaron una sola vez.
- Escalado: con carga sostenida el servicio pasó de 1 a 3 tareas. Las tres quedaron `healthy` en las dos subredes privadas.
- Defecto corregido durante la prueba: los eventos sin atributo `inscritos` no devolvían el campo y el sitio mostraba `undefined/30 lugares`. Ahora se devuelve `0`.

## Estructura del proyecto

```
template.yaml                # CloudFormation: VPC, endpoints, ECS, ALB, DynamoDB, ECR, S3
src/
  Dockerfile                 # Imagen Python 3.12-slim con Uvicorn en el puerto 8000
  requirements.txt           # fastapi, uvicorn, boto3, apscheduler
  app/
    main.py                  # Aplicación FastAPI, CORS y ciclo de vida (planificador)
    config.py                # Variables de entorno
    scheduler.py             # Planificador APScheduler (cada hora)
    routers/                 # Rutas HTTP (/health, /eventos, /inscripciones)
    services/                # Lógica de negocio: cupos, inscripciones, recordatorios
  inscribir/, listar_eventos/, recordatorio/, mis_inscripciones/
                             # Versión anterior con Lambda. No entra en la imagen.
                             # Pendiente: eliminar junto con sus pruebas.
scripts/
  build_and_push.sh / .bat   # Build de la imagen y push a ECR
  seed_eventos.py            # Carga de eventos de prueba
web/                         # Sitio en Vite + React
tests/                       # Pruebas unitarias
docs/                        # Documento, informe, presentación y diagramas
```

## Notas de diseño

- **Fargate**: no hay servidores EC2 que administrar. El costo es fijo por tarea mientras está encendida.
- **Red sin NAT**: las tareas solo hablan con servicios de AWS, y para eso bastan los endpoints. Un NAT Gateway cobraría por hora sin aportar nada hoy. Si una tarea necesitara salir a Internet, se agrega entonces.
- **Cupos concurrentes**: `ADD inscritos :uno` con condición `inscritos < cupo`, directo en DynamoDB. Funciona entre tareas porque la condición la evalúa DynamoDB.
- **Recordatorios dentro de la tarea**: EventBridge podría disparar una tarea ECS, pero necesita un rol que Academy no permite crear. El planificador queda en la aplicación y el reclamo por evento evita duplicados.
- **Roles IAM**: en AWS Academy `LabRole` cumple los dos papeles (ejecución y tarea). En producción se separan en roles de mínimo privilegio (ver `docs/Informe.md`, sección 6).

## Limitaciones conocidas

- La API no tiene autenticación. `GET /inscripciones?email=` responde a cualquiera que conozca el correo.
- El sitio y el ALB usan HTTP. CloudFront está denegado en Academy, y el HTTPS del ALB requiere un certificado que no se probó.
- Sin WAF ni límites de tasa.
- El contenedor corre como root.
- Una sola región. DynamoDB no tiene respaldos automáticos (point-in-time recovery no está activado).
- Si la publicación de un recordatorio falla, la marca se libera y se reintenta en la siguiente hora. Un fallo de la tarea entre el reclamo y la publicación puede dejar un recordatorio sin enviar.
