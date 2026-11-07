# Presentación del sistema de inscripción y recordatorios para eventos

Duración de 10 minutos. No hace falta mostrar la aplicación en vivo. El tiempo de cada bloque suma 9 minutos y 30 segundos, y los 30 segundos restantes son margen.

## 1. Qué es la aplicación (1 minuto)

En la diapositiva van el título, el problema y la solución en una línea.

Texto guía. Es un sitio donde la gente ve los eventos disponibles, se inscribe y recibe un correo de confirmación. Antes de cada evento, recibe un recordatorio por correo. El backend corre en contenedores administrados con Amazon ECS y AWS Fargate, dentro de una VPC propia, sin necesidad de aprovisionar ni administrar máquinas virtuales EC2.

## 2. Arquitectura (1 minuto 30 segundos)

En la diapositiva va el diagrama de componentes y de tráfico (`docs/diagrama-arquitectura.png`). Si hay tiempo, el de red (`docs/diagrama-red.png`).

Texto guía. El usuario abre un sitio estático en S3. La página llama a la API a través de un Application Load Balancer (ALB) público. El ALB reparte las peticiones entre las tareas de un servicio de Amazon ECS con Fargate, que ejecutan una aplicación FastAPI en Python 3.12. Las tareas están en subredes privadas, sin ruta a Internet, y hablan con DynamoDB, SNS, ECR y CloudWatch Logs por endpoints de VPC. Cada tarea tiene un planificador que se ejecuta cada hora y envía los recordatorios de los eventos de las próximas 24 horas. Un reclamo condicional en DynamoDB evita que dos tareas envíen el mismo recordatorio.

## 3. Cómo no se cae, y qué pasa si se cae (2 minutos)

En la diapositiva va la tabla de fallas resumida (sección 4.2 del informe).

Texto guía, en orden.

1. Una zona de disponibilidad falla. El ALB y las tareas están repartidos en dos zonas. Con dos o más tareas, el ALB sigue atendiendo desde la zona sana. DynamoDB replica los datos en tres zonas de la región, según su documentación. Con una sola tarea, la caída de su zona deja el servicio sin respuesta hasta que ECS la reprograma. Esa es la decisión de costo que explico en el punto 4.
2. Una tarea se detiene o falla. El health check del ALB en `/health` deja de enviarle tráfico, y ECS reprograma una tarea nueva para mantener la cantidad deseada. Es el comportamiento documentado de ECS. Todavía no lo demostramos en esta entrega, así que lo presento como pendiente de prueba.
3. El recordatorio falla en una ejecución. Si la publicación falla, la marca se libera y el envío se reintenta en la siguiente hora, porque la ventana de búsqueda es de 24 horas. Si la tarea se cae justo entre el reclamo y la publicación, ese recordatorio puede no salir. Es una limitación conocida.
4. Concurrencia de inscripciones. El incremento atómico condicional en DynamoDB (`inscritos < cupo`) impide la sobreventa aunque varias tareas reciban inscripciones a la vez. En la prueba, 12 inscripciones simultáneas a un evento de cupo 10 dieron 10 respuestas 201 y 2 respuestas 409.

## 4. Limitaciones y roles IAM (1 minuto 30 segundos)

En la diapositiva van cinco puntos clave de límites y permisos.

Texto guía.

- El mínimo de 1 tarea es una decisión de costo. Con dos tareas repartidas en dos zonas, la falla de una zona queda cubierta sin interrupción. Ese es el cambio que haríamos para producción.
- En AWS Academy no se pueden crear roles IAM, así que el rol de ejecución y el de la tarea son el `LabRole` preexistente. En producción se separan en roles de mínimo privilegio. Uno es `ecsTaskExecutionRole`, para descargar la imagen y escribir logs. El otro es `backendEventosTaskRole`, acotado a las tablas y al topic del sistema.
- La API no tiene autenticación. Quien conoce un correo ve sus inscripciones. Para la demo académica alcanza; en producción llevaría Cognito o JWT.
- El sitio y el balanceador usan HTTP, porque en Academy no hay dominio propio ni certificados de ACM, y CloudFront está denegado.
- El correo de inscripción solo llega a quien confirmó la suscripción de SNS.

## 5. Por qué es seguro (1 minuto 30 segundos)

En la diapositiva va la tabla de canales y controles de red.

Texto guía. El ALB es el único punto de entrada a la API, con su grupo de seguridad abierto solo en el puerto 80. Las tareas están en subredes privadas, sin IP pública y sin ruta a Internet. Su grupo de seguridad acepta el puerto 8000 únicamente desde el ALB. Hablan con DynamoDB, SNS, ECR y CloudWatch Logs por HTTPS a través de endpoints de VPC, que mantienen el tráfico dentro de la red de AWS. DynamoDB cifra los datos en reposo. No hay credenciales ni secretos en el código. Las credenciales temporales vienen del rol asignado a la tarea. Lo que falta es HTTPS en el borde y autenticación en la API, y lo digo en el punto 4.

## 6. Cómo escala (1 minuto 30 segundos)

En la diapositiva va la tabla de la prueba de escalado, con 1 tarea, luego 2 y luego 3, y el CPU de cada etapa.

Texto guía. Fargate evita administrar servidores y parchear el sistema operativo. El servicio arranca con 1 tarea y puede llegar a 3. Application Auto Scaling sigue el CPU promedio del servicio con un objetivo de 60 %. Sube de a una tarea con un cooldown de 60 segundos y baja con un cooldown de 300 segundos. Sube solo con carga sostenida, porque un pico corto no alcanza para disparar la política.

Dato verificado. Con 60 conexiones paralelas, el CPU llegó a entre 75 y 83 % durante tres minutos. La capacidad pasó de 1 a 2 y luego a 3 tareas, y las tres quedaron `healthy` repartidas en las dos subredes privadas.

## 7. Cierre (30 segundos)

Texto guía. El sistema funciona sobre ECS con Fargate, FastAPI y DynamoDB, con tareas en dos zonas, escalado verificado de 1 a 3 tareas y pruebas de concurrencia y de recordatorios. Tiene límites conocidos, como el mínimo de 1 tarea por costo, la falta de autenticación y el uso de HTTP. Están documentados, con su alternativa. Al terminar, el stack se elimina para no dejar cobros activos.

## Preguntas probables

- ¿Por qué ECS Fargate y no EC2? Porque Fargate elimina la administración de instancias, los parches de seguridad y el dimensionamiento de la capacidad del clúster.
- ¿Por qué el planificador corre dentro de la tarea y no como una tarea programada desde afuera? Porque en AWS Academy no se pueden crear los roles de IAM que necesita un disparador externo para ejecutar tareas. El planificador queda en la aplicación, y el reclamo condicional evita envíos duplicados entre tareas.
- ¿Por qué no hay al menos 2 tareas si la aplicación usa dos zonas? Es una decisión de costo. Con 1 tarea, la falla de su zona o su reemplazo corta el servicio hasta que ECS la reprograma. Con 2 tareas en dos zonas se cubre la falla de una zona, y es el cambio que haríamos en producción.
- ¿Cuándo escala? Cuando el CPU promedio se mantiene por encima del 60 %, hasta un máximo de 3 tareas. Se verificó la subida de 1 a 3 con carga sostenida.
- ¿Qué roles harían falta en producción real? Harían falta dos roles independientes, un rol de ejecución para ECR y CloudWatch, y un rol de tarea acotado a DynamoDB y SNS.
- ¿Qué pasa si una tarea se cae? ECS reprograma una tarea nueva para mantener la cantidad deseada, y el ALB no le envía tráfico hasta que `/health` responda 200. Es el comportamiento documentado de ECS; falta demostrarlo con una falla provocada.
