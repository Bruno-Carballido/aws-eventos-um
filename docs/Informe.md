# Informe del proyecto: sistema de inscripción y recordatorios para eventos

Este informe amplía el documento del proyecto con el detalle que pide la consigna:
arquitectura, seguridad, escalabilidad, resiliencia, costos y permisos de IAM.
Todo lo que describe está desplegado y probado en AWS Academy, salvo que se indique
lo contrario en la sección 7.

## 1. Arquitectura

### 1.1 Componentes

| Componente | Servicio | Función |
|---|---|---|
| Sitio | Amazon S3 (website endpoint) | Entrega la página React compilada. |
| API | Amazon API Gateway (HTTP API) | Expone `GET /eventos`, `POST /inscripciones` y `GET /inscripciones?email=`. |
| Lógica | AWS Lambda (Python 3.12, cuatro funciones) | Listar eventos, inscribir, consultar inscripciones y enviar recordatorios. |
| Datos | Amazon DynamoDB (tablas `Eventos` e `Inscripciones`) | Eventos, cupos e inscripciones. Índices `porEvento` y `porEmail`. |
| Notificaciones | Amazon SNS (un topic por evento) | Correos de confirmación y de recordatorio. |
| Programación | Regla programada de Amazon EventBridge | Dispara `Recordatorio` cada hora. |
| Fallos | Amazon SQS (cola DLQ) | Recibe los eventos programados que fallan tras los reintentos. |
| Observabilidad | Amazon CloudWatch Logs | Logs y errores de las funciones y de la API. |

### 1.2 Flujo de tráfico

1. El usuario abre el sitio en S3. La página consulta la API.
2. API Gateway invoca `ListarEventos`, que lee la tabla `Eventos`.
3. Al inscribirse, API Gateway invoca `Inscribir`. La función valida el evento, evita
   duplicados, incrementa el contador de cupo de forma condicional y guarda la
   inscripción.
4. `Inscribir` suscribe el correo al topic del evento y publica el mensaje de
   confirmación.
5. Cada hora, EventBridge invoca `Recordatorio`. La función busca los eventos de las
   próximas 24 horas, publica el recordatorio en el topic y marca el evento como
   notificado.
6. Si una ejecución programada falla dos veces, EventBridge envía el evento a la DLQ.
7. Todas las funciones escriben en CloudWatch Logs.

Los tres diagramas están en `docs/`. El de componentes y tráfico es `diagrama-arquitectura.png`.
El de red, con el alcance público y privado, es `diagrama-red.png`. El de seguridad,
con zonas de confianza, controles y debilidades, es `diagrama-seguridad.png`.

### 1.3 Decisiones de diseño

- Serverless de punta a punta. No hay servidores que administrar ni instancias que
  mantener encendidas.
- Las funciones no están en una VPC. Ningún recurso del proyecto es privado, así que
  una VPC sumaría subredes, NAT y endpoints sin aportar seguridad real.
- Un topic de SNS por evento. Así, cada inscripto recibe solo los mensajes de los
  eventos a los que se inscribió.
- La confirmación no bloquea la respuesta HTTP. La API responde apenas se guarda la
  inscripción.

## 2. Seguridad

### 2.1 Redes públicas y privadas

Todo el sistema usa endpoints públicos de AWS, protegidos con IAM y HTTPS. No hay
redes privadas porque no hay recursos que deban quedar ocultos.

| Canal | Protocolo | Exposición | Control |
|---|---|---|---|
| Usuario hacia S3 | HTTP | Pública | Política de bucket de solo lectura |
| Usuario hacia API Gateway | HTTPS | Pública | CORS abierto para la demo |
| API Gateway hacia Lambda | Interno de AWS | Privado | Política de recurso de la función |
| Lambda hacia DynamoDB, SNS y SQS | HTTPS | Privado | IAM con mínimo privilegio |
| SNS hacia el correo del usuario | SMTP | Pública | Suscripción confirmada por el usuario |

Las funciones corren fuera de una VPC. Si el proyecto se llevara a una VPC, haría
falta una subred privada, endpoints de DynamoDB y S3, endpoints de interfaz para SNS
y SQS, y un NAT Gateway si alguna función necesitara salir a Internet.

### 2.2 Security groups y control de acceso

El proyecto no tiene security groups. Un security group protege recursos dentro de
una VPC, y aquí no hay recursos en una VPC. El control de acceso recae en IAM:

- `ListarEventos` solo lee la tabla `Eventos`.
- `Inscribir` lee y escribe ambas tablas, y publica en SNS.
- `MisInscripciones` solo lee la tabla `Inscripciones`.
- `Recordatorio` lee `Eventos`, actualiza el atributo `notificado`, publica en SNS
  y envía mensajes a la DLQ.
- La regla de EventBridge solo puede invocar la función `Recordatorio`.
- La cola DLQ solo acepta mensajes de EventBridge de esta cuenta.

### 2.3 Protocolos y cifrado

- La API usa HTTPS. API Gateway no sirve el endpoint por HTTP.
- El sitio usa HTTP. El website endpoint de S3 no admite HTTPS propio. Esta es la
  debilidad más visible del sistema.
- DynamoDB cifra los datos en reposo por defecto. Las conexiones de las funciones a
  DynamoDB, SNS y SQS usan TLS.
- No hay llaves ni contraseñas en el código. La configuración viaja en variables de
  entorno y las credenciales las entrega el rol de ejecución.
- Secrets Manager no se usa porque el proyecto no maneja secretos de terceros. Si se
  integrara un proveedor externo con API key, se guardaría en Secrets Manager o en
  Parameter Store.

### 2.4 Límites de seguridad conocidos

- La API no tiene autenticación. `GET /inscripciones?email=` devuelve las
  inscripciones de cualquier email que alguien conozca. En producción iría detrás de
  Amazon Cognito o de un autorizador JWT.
- El sitio no tiene HTTPS. En producción, CloudFront con Origin Access Control
  resolvería el HTTPS y permitiría un bucket privado. En Academy, CloudFront está
  denegado (sección 6).
- La respuesta de `GET /inscripciones` incluye el nombre del inscripto, aunque el
  contrato original pedía solo cinco campos.
- No hay límite de tasa configurado por ruta. Un cliente puede enviar peticiones en bucle hasta la cuota general de la cuenta.
- Los logs no imprimen correos ni nombres. La función `Recordatorio` imprime solo
  IDs de evento.

## 3. Escalabilidad

### 3.1 Modelo elegido

El sistema escala sin instancias que el equipo administre. La alternativa clásica
sería EC2 con un Auto Scaling group detrás de un balanceador. Para esta carga no
conviene, por tres motivos:

1. Una instancia encendida cobra por hora aunque nadie use el sistema.
2. La alta disponibilidad con EC2 exige al menos dos instancias en dos zonas de
   disponibilidad, un balanceador y, si hay subredes privadas, un NAT Gateway por
   zona. Cada pieza cobra por hora.
3. El Auto Scaling group reacciona con retraso. Escala por métricas de CPU o de
   solicitudes que se promedian en minutos, mientras que Lambda crea entornos por
   solicitud.

ECS con Fargate tiene el mismo problema de costo fijo. No se usa ni EC2 ni ECS en
este proyecto.

### 3.2 Qué escala y con qué mecanismo

| Componente | Cómo escala | Límite a considerar |
|---|---|---|
| API Gateway | Acepta solicitudes según la demanda | Cuota de solicitudes por segundo de la cuenta. |
| Lambda | Crea un entorno de ejecución por solicitud concurrente | Concurrencia total de la cuenta por región. |
| DynamoDB en modo pago por petición | Reparte la capacidad automáticamente | Sin cuota práctica para esta carga. Hay límites por partición. |
| SNS | Publica a los suscriptores en paralelo | Cuota de publicaciones por segundo. |
| Recordatorio | Una ejecución por hora, sin escalado | No aplica. |

### 3.3 Cuándo se enciende y cuándo se apaga

- No hay instancias encendidas. Cada solicitud activa una ejecución de Lambda y la
  libera al terminar.
- En un pico de inscripciones, Lambda crea más entornos en paralelo. DynamoDB absorbe
  las escrituras. El contador de cupo sigue siendo exacto porque el incremento es
  condicional.
- Cuando no hay tráfico, el costo es cero. Solo se paga por ejecución y por
  almacenamiento.
- El recordatorio corre 24 veces por día. Su carga no depende de los usuarios.
- El primer arranque de una función fría tarda más. Es el costo de no mantener
  instancias encendidas.

### 3.4 Qué pasa con un pico de demanda

Supongamos que se abren las inscripciones de un evento con 500 lugares y 2 000
personas lo intentan en un minuto. Las solicitudes llegan a la API, Lambda crea
entornos en paralelo y cada inscripción intenta incrementar el contador. Las que
llegan después de agotarse el cupo reciben un 409 sin escribir nada. Los correos se
publican en SNS sin frenar la respuesta. El límite real sería la concurrencia de la
cuenta, no la cantidad de instancias.

### 3.5 TCO comparado

El costo total de propiedad compara cuánto cuesta mantener el sistema, no solo
cuánto cuesta cada recurso.

| Concepto | Serverless (esta solución) | EC2 con ASG y balanceador |
|---|---|---|
| Cómputo | Por ejecución | Por hora de cada instancia, 24 horas al día |
| Red de alta disponibilidad | Incluida en el servicio | Balanceador, NAT Gateway por zona |
| Parcheo y sistema operativo | No aplica | A cargo del equipo |
| Escalado | Automático | Configurado y probado por el equipo |
| Costo ocioso | Cero | Mínimo de instancias encendidas |

No calculé el monto exacto de la alternativa. Hacerlo con la calculadora de precios
de AWS es un paso pendiente (sección 7).

## 4. Resiliencia

### 4.1 Diseño multi-zona de disponibilidad

El requisito pide multi-AZ. En este proyecto la redundancia en varias zonas de
disponibilidad la aportan los servicios gestionados. No la configuramos nosotros con
subredes, porque no hay subredes. Lo que sigue describe cada servicio.

- DynamoDB replica automáticamente los datos en tres zonas de disponibilidad de la
  región. AWS publica un SLA de disponibilidad de 99,99 por ciento [4].
- SNS usa zonas de disponibilidad separadas dentro de la región y permite reintentos
  y colas de mensajes fallidos en las suscripciones [5].
- Lambda ejecuta las funciones en varias zonas de disponibilidad de la región.
  Esta afirmación no quedó citada en esta revisión y debe verificarse antes de la
  defensa.
- API Gateway y SQS son servicios regionales gestionados con redundancia interna.
  No los cité en esta revisión.
- S3 almacena los objetos en varias zonas. Tampoco lo cité en esta revisión.

Lo que no cubre el diseño es una caída de la región entera. El sistema usa una sola
región (us-east-1, la que permite Academy). Para resistirla habría que replicar a una
segunda región con DynamoDB global tables y repetir el despliegue allí.

### 4.2 Qué pasa en cada falla

| Falla | Efecto para el usuario | Efecto en los datos | Cómo se recupera |
|---|---|---|---|
| Una zona de disponibilidad | Ninguno visible. | Ninguno. | Automático, por los servicios gestionados. |
| API Gateway o Lambda devuelven error | La página muestra "No se pudo conectar con la API" y ofrece reintentar. | Depende del punto de falla (ver las filas siguientes). | El usuario reintenta. |
| Falla antes de escribir la inscripción | Error 500. | Nada guardado. | El usuario reintenta. |
| Falla después de incrementar el cupo y antes de guardar la inscripción | Error 500. | El cupo se pierde. | Hoy no se corrige solo. Es un defecto conocido (sección 7). |
| Falla después de guardar, al publicar en SNS | Error 500, aunque la inscripción existe. | La inscripción queda guardada sin correo. | Al reintentar, la API responde 409 "ya está inscripto" y el correo nunca llega. Es un defecto conocido. |
| `Recordatorio` falla | Ninguno inmediato. | Sin cambios. | EventBridge reintenta dos veces con una edad máxima de una hora. Si sigue fallando, el evento va a la DLQ. |
| Se pierde una ejecución horaria | El recordatorio sale en la siguiente ejecución. | Ninguno. | La ventana de 24 horas cubre una ejecución perdida. |
| Borrado o escritura accidental en DynamoDB | Datos incorrectos o faltantes. | Pérdida posible. | Hoy no hay respaldos. Recomendación: activar point-in-time recovery [4]. |
| Correo de confirmación no confirmado | El inscripto no recibe el correo de inscripción. | Ninguno. | Requiere confirmar el clic de SNS. Es una limitación de SNS. |
| Caída de la región | El sistema no responde. | Los datos quedan en la región. | Fuera del alcance de la demo. |

### 4.3 Objetivos de recuperación

- El tiempo de recuperación (RTO) no está definido. Las fallas transitorias se corrigen
  reintentando. Los eventos que llegan a la DLQ requieren intervención manual.
- El punto de recuperación (RPO) no está definido. Sin point-in-time recovery, el RPO
  de un borrado accidental es todo el historial posterior.

## 5. Costos

El diseño es de pago por uso. Con la carga de la demo, el costo queda muy por debajo
de un dólar por mes.

- Lambda ofrece un millón de solicitudes y 400 000 GB-segundo gratis por mes [1].
- DynamoDB en modo pago por petición cobra por lectura y escritura [2].
- SNS cobra por solicitudes de API y por entregas de notificaciones [3].
- API Gateway y EventBridge cobran por invocación. Estas tarifas no están citadas en
  esta revisión.
- Los costos de error están acotados. La DLQ evita reintentos infinitos y el atributo
  `notificado` evita envíos repetidos.

Con un presupuesto de créditos limitado conviene evitar servicios que cobran por hora
aunque no se usen. Por eso el proyecto descarta EC2, balanceadores y NAT Gateway.

## 6. Roles y permisos con un rol distinto de LabRole

Academy entrega un único rol, `LabRole`, a todas las funciones. Esto significa que
cada función tiene más permisos de los que necesita. Un despliegue fuera de Academy
crearía un rol por función, con permisos mínimos.

| Servicio o función | Por qué no alcanza LabRole | Estado |
|---|---|---|
| CloudFront con Origin Access Control | Academy lo deniega: `cloudfront:CreateOriginAccessControl`. | Verificado el 7 de noviembre. |
| Un rol de ejecución por función | La guía de Academy restringe crear roles. Con un rol propio, cada función tendría solo sus permisos. | Restricción documentada del lab. No probado en esta sesión. |
| Autenticación de usuarios (Cognito) | Crear un user pool y un autorizador necesita permisos de Cognito. | No probado en Academy. |
| VPC, subredes y endpoints | Crear redes necesita permisos de EC2 de red. | No probado en Academy. |
| Correos desde una cuenta propia (SES) | El envío a direcciones arbitrarias suele estar restringido. | No probado en esta sesión. |
| Secrets Manager | No hace falta hoy. Si se agregara un proveedor externo, sí. | No aplica. |
| AWS WAF y límites de tasa | Requieren permisos de WAF. | No probado en Academy. |

Un rol propio por función reemplazaría el parámetro `RolEjecucion` por cuatro roles,
cada uno con su política mínima. Ese cambio requiere
un rol que pueda crear y asumir roles (`iam:CreateRole` e `iam:PassRole`), que
Academy no ofrece.

## 7. Limitaciones y pendientes

Limitaciones del sistema:

- Sin autenticación. Cualquiera que conozca un email puede consultar sus inscripciones.
- El sitio usa HTTP, porque CloudFront está denegado en Academy.
- El correo de inscripción solo llega a quien ya confirmó la suscripción de SNS.
- Una falla entre el cupo y el guardado puede consumir un lugar sin inscripción.
- Una falla al publicar en SNS deja la inscripción sin correo y con respuesta de error.
- `cupo=0` en un evento sin contador previo puede vender un lugar.
- `ListarEventos` y `Recordatorio` leen la tabla completa. Sirve para un catálogo
  chico, no para uno grande.
- Sin point-in-time recovery ni respaldos.
- Una sola región.

Pendientes antes de la entrega:

- Calcular el TCO de la alternativa EC2 con la calculadora de precios de AWS.
- Citar la documentación de Lambda y de API Gateway sobre multi-AZ.
- Activar point-in-time recovery en el template.

Decisiones tomadas:

- Los defectos de la sección 4.2 se presentan como limitaciones. No se corrigen antes
  de la entrega.
- El proyecto no usa ECS ni EC2. La consigna no lo exige y el diseño serverless
  cubre el alcance.

## 8. Fuentes

[1] https://aws.amazon.com/lambda/pricing
[2] https://aws.amazon.com/dynamodb/pricing
[3] https://aws.amazon.com/sns/pricing
[4] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/disaster-recovery-resiliency.html
[5] https://docs.aws.amazon.com/sns/latest/dg/sns-resilience.html
