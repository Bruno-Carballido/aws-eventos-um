# Presentación: sistema de inscripción y recordatorios para eventos

Duración de 10 minutos. No hace falta mostrar la aplicación en vivo. El tiempo de cada
bloque suma 9 minutos y 30 segundos, y los 30 segundos restantes son margen.

## 1. Qué es la aplicación (1 minuto)

En la diapositiva van el título, el problema y la solución en una línea.

Texto guía. Es un sitio donde la gente ve los eventos disponibles, se inscribe y
recibe un correo de confirmación. Antes de cada evento, recibe un recordatorio por
correo. Todo corre en AWS con servicios administrados. No hay servidores que
mantener.

## 2. Arquitectura (1 minuto 30 segundos)

En la diapositiva va el diagrama de componentes y de tráfico (`docs/diagrama-arquitectura.png`).

Texto guía. El usuario abre un sitio en S3. Ese sitio llama a una API en API
Gateway. La API activa funciones Lambda, que guardan los datos en DynamoDB y envían
correos con SNS. Una regla de EventBridge revisa cada hora qué eventos ocurren en las
próximas 24 horas y manda los recordatorios. CloudWatch guarda los logs.

## 3. Cómo no se cae, y qué pasa si se cae (2 minutos)

En la diapositiva va la tabla de fallas resumida (sección 4.2 del informe).

Texto guía, en orden.

1. Una zona de disponibilidad falla. Nadie lo nota, porque DynamoDB replica los datos
   en tres zonas de la región y SNS reparte sus mensajes entre zonas.
2. La API o una función falla. El usuario ve un mensaje de error con un botón para
   reintentar. En la mayoría de los casos no se pierde ningún dato. La excepción es
   el cupo, explicada más abajo.
3. El recordatorio falla. EventBridge reintenta dos veces. Si sigue fallando, el
   evento queda en una cola de mensajes fallidos durante 14 días para revisarlo.
4. Se pierde una ejecución horaria. El recordatorio sale en la siguiente, porque la
   ventana es de 24 horas y no de una hora.

Decir con claridad lo que no está resuelto: una falla entre el cupo y el guardado
puede consumir un lugar. Una falla al publicar en SNS deja la inscripción sin correo.
Son defectos conocidos y están en la sección 7 del informe.

## 4. Limitaciones (1 minuto 30 segundos)

En la diapositiva van cinco limitaciones.

Texto guía.

- La API no tiene autenticación. Quien conoce un correo ve sus inscripciones.
- El sitio usa HTTP. CloudFront, que daría HTTPS, está denegado en AWS Academy.
- El correo de inscripción solo llega a quien confirmó la suscripción de SNS. El
  primer correo que recibe es el de confirmación de SNS, y su texto no se puede
  cambiar.
- Hay una sola región y no hay respaldos automáticos de DynamoDB.
- El sistema corre con un único rol compartido, LabRole, porque Academy no permite
  crear roles propios.

## 5. Por qué es seguro (1 minuto 30 segundos)

En la diapositiva va la tabla de canales y controles.

Texto guía. Todo lo que es público está pensado para serlo. El sitio y la API son
públicos, y el resto del sistema es privado. Las funciones no están en una VPC porque
no tienen recursos privados que proteger. El control de acceso lo hace IAM. La API usa HTTPS. DynamoDB cifra los datos en
reposo. No hay contraseñas en el código.

El diseño da a cada función solo los permisos que usa. En Academy todas comparten
LabRole, así que el control fino requiere un rol por función, y Academy no lo permite.

## 6. Cómo escala (1 minuto 30 segundos)

En la diapositiva va una línea de tiempo con un pico de inscripciones.

Texto guía. No hay instancias encendidas. Cada solicitud activa una ejecución y la
libera al terminar. Con un pico de inscripciones, Lambda crea más ejecuciones en
paralelo y DynamoDB absorbe las escrituras. El contador de cupo sigue siendo exacto
porque cada incremento es condicional. Cuando no hay tráfico, el costo es cero.

Comparar con EC2: harían falta dos instancias en dos zonas, un balanceador y, si
hubiera subredes privadas, un NAT Gateway por zona. Todo eso cobra por hora, aunque
nadie use el sistema.

## 7. Cierre (30 segundos)

Texto guía. El sistema hace lo que pide la consigna, con servicios administrados que
tienen redundancia en varias zonas. Tiene límites conocidos, como la falta de
autenticación y del HTTPS del sitio, y eso está documentado. Sabemos qué se mejoraría
en producción.

## Preguntas probables

- ¿Por qué no EC2 con Auto Scaling? Porque cobra por hora sin uso y reacciona más
  lento que Lambda ante un pico.
- ¿Por qué las Lambdas no están en una VPC? Porque no acceden a recursos privados. Una
  VPC sumaría subredes, NAT y endpoints sin agregar seguridad real.
- ¿Qué pasa si se cae la región? El sistema no responde. Para resistirlo habría que
  replicar en una segunda región con DynamoDB global tables.
- ¿Cómo se restaura un dato borrado por error? Hoy no se puede. Point-in-time recovery
  lo permitiría, y es una mejora pendiente.
- ¿Por qué no hay Secrets Manager? El proyecto no maneja secretos de terceros. Las
  credenciales las entrega el rol. Si se integrara un proveedor con API key, se
  guardaría en Secrets Manager.
