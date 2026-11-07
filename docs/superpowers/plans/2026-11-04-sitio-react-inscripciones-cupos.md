# Sitio React + Mis Inscripciones + Cupos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el sitio HTML/JS a mano por una versión Vite + React pulida (visual/UX) y agregar dos funcionalidades end-to-end: "mis inscripciones" por email y contador de cupos con bloqueo al llenarse.

**Architecture:** El backend suma un endpoint (`GET /inscripciones?email=`) y un contador atómico de cupos en `Eventos`; el frontend pasa a un proyecto Vite + React cuyo `dist/` se sirve desde S3. El contrato API existente (`GET /eventos`, `POST /inscripciones`) se mantiene, solo se agregan campos y un endpoint.

**Tech Stack:** Python 3.12 (Lambda), AWS SAM, DynamoDB, SNS; Vite + React (JSX, sin framework UI), CSS moderno.

**Spec:** `docs/Documento del proyecto.md` + diseño aprobado en conversación (2026-11-04): pulido visual/UX + mis inscripciones + contador de cupos.

## Global Constraints

- Sin backend nuevo de autenticación; `GET /inscripciones?email=` es público (limitación documentada).
- `web/` queda como proyecto Vite; `web/dist/` se commitea al repo; el deploy en Academy es `aws s3 cp web/dist/`.
- `API_URL` es una constante en `web/src/config.js`, ajustable tras el deploy.
- Tests Python con stdlib `unittest` + `unittest.mock` (sin dependencias nuevas para testear); stub de `boto3` vía `sys.modules` antes de importar el módulo.
- No se rompe `POST /inscripciones` existente: solo se agregan campos (`tituloEvento`) y el 409 por cupo lleno.
- Lenguaje de la UI: español. Comunicaciones del proyecto en español.

## Review Focus

1. **Dos inscripciones simultáneas en el último lugar** → el incremento debe ser condicional (`inscritos < cupo`) y el 409 debe llegar sin dejar inscripción huérfana → test en Task 1 (cupos llenos tras éxito previo).
2. **Evento sin atributo `inscritos` (creado antes del cambio)** → el contador debe tratarlo como 0, no fallar → test en Task 1 (evento con cupo pero sin inscritos).
3. **`GET /inscripciones` sin email o email inválido** → 400, nunca un scan completo → test en Task 2.
4. **Email con casing/espacios distintos** (`  Bruno@Gmail.com ` vs `bruno@gmail.com`) debe encontrar las mismas inscripciones → normalizar a `strip().lower()` en ambos endpoints → test en Task 1 y Task 2.
5. **Frontend con API caída o URL sin configurar** → la UI muestra un error legible, no una pantalla en blanco → verificación manual en Task 4.

---

### Task 1: Cupos — modelo, listado con contador y bloqueo en inscripción

**Files:**
- Modify: `scripts/seed_eventos.py` (agregar `cupo` a los 3 eventos de prueba)
- Modify: `src/listar_eventos/app.py` (incluir `cupo` e `inscritos` en la proyección)
- Modify: `src/inscribir/app.py` (incremento condicional del contador, `tituloEvento` en la inscripción)
- Test: `tests/test_cupos.py` (nuevo)

**Interfaces:**
- Consumes: tablas `Eventos` e `Inscripciones` existentes.
- Produces: `GET /eventos` devuelve items con `cupo` (int) e `inscritos` (int, ausente = 0); `POST /inscripciones` responde 409 `{"error": "sin cupos disponibles"}` cuando `inscritos >= cupo`; item de inscripción incluye `tituloEvento` (str).

- [ ] **Step 1: Escribir los tests fallidos** en `tests/test_cupos.py`:

```python
def test_listar_incluye_cupo_e_inscritos()          # scan devuelve cupo=30, inscritos=12 → pasan al JSON
def test_inscribir_ok_incremente_contador()          # update condicional ADD inscritos :1 sobre evento
def test_inscribir_sin_cupos_devuelve_409()          # ConditionalCheckFailedError del update → 409 y NO put_item
def test_evento_sin_atributo_inscritos_cuenta_como_cero()  # update con attribute_not_exists(inscritos) OR inscritos < cupo
def test_inscribir_normaliza_email()                 # " A@B.com " → "a@b.com" en el item guardado
```

Usar `unittest` con `mock.patch` sobre `boto3.resource`/`boto3.client` y stub de `sys.modules['boto3']` antes del import si boto3 no está instalado.

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `python -m unittest tests.test_cupos -v`
Expected: FAIL (funciones sin los cambios, import errors)

- [ ] **Step 3: Implementar los cambios**

- `seed_eventos.py`: cada evento de prueba gana `"cupo": <int>` (30, 25, 10).
- `listar_eventos/app.py`: agregar `cupo,inscritos` a `ProjectionExpression`.
- `inscribir/app.py`: después del check de duplicados y antes del `put_item`, hacer `update_item` sobre `Eventos` con `UpdateExpression="ADD inscritos :uno"` y `ConditionExpression="attribute_not_exists(inscritos) OR inscritos < :cupo"` (valores `:uno=1`, `:cupo=<cupó del evento leído>`). Capturar `botocore.exceptions.ClientError` con código `ConditionalCheckFailedException` → `return _resp(409, {"error": "sin cupos disponibles"})` sin insertar. El `put_item` agrega `"tituloEvento": evento["titulo"]`.

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `python -m unittest tests.test_cupos -v`
Expected: PASS (5/5)

- [ ] **Step 5: Commit**

```bash
git add tests/test_cupos.py src/inscribir/app.py src/listar_eventos/app.py scripts/seed_eventos.py
git commit -m "feat: contador de cupos con bloqueo atomico"
```

### Task 2: Endpoint Mis Inscripciones

**Files:**
- Create: `src/mis_inscripciones/app.py`
- Modify: `template.yaml` (función `MisInscripciones`, evento `GET /inscripciones`, política DynamoDB read)
- Test: `tests/test_mis_inscripciones.py` (nuevo)

**Interfaces:**
- Consumes: tabla `Inscripciones` con GSI `porEmail` (Task 1 deja `tituloEvento` en los items).
- Produces: `GET /inscripciones?email=<str>` → 200 `[{inscripcionId, eventoId, tituloEvento, email, creadoEn}]`; 400 si falta el email.

- [ ] **Step 1: Escribir los tests fallidos** en `tests/test_mis_inscripciones.py`:

```python
def test_consulta_por_email_devuelve_inscripciones()   # query al GSI porEmail con email normalizado
def test_email_faltante_devuelve_400()                 # sin querystring → 400
def test_email_normalizado()                           # " A@B.com " → "a@b.com" en la query
```

Mismo patrón de stub que Task 1.

- [ ] **Step 2: Correr y verificar FAIL**

Run: `python -m unittest tests.test_mis_inscripciones -v`
Expected: FAIL (módulo no existe)

- [ ] **Step 3: Implementar `handler(event, context) -> dict` en `src/mis_inscripciones/app.py`**

Lee `queryStringParameters.email`; sin email → `_resp(400, ...)`. Con email: `strip().lower()`, `query` sobre IndexName `porEmail` con `email = :m`, ordena por `creadoEn` descendente, devuelve 200 con la lista. Reutilizar el patrón `_resp` de las otras lambdas.

En `template.yaml`: recurso `MisInscripciones` (Handler `mis_inscripciones/app.handler`, CodeUri `src/mis_inscripciones`) con evento HttpApi `GET /inscripciones` y política `DynamoDBReadPolicy` sobre `TablaInscripciones`.

- [ ] **Step 4: Correr y verificar PASS**

Run: `python -m unittest tests.test_mis_inscripciones -v`
Expected: PASS (3/3)

- [ ] **Step 5: Commit**

```bash
git add src/mis_inscripciones/app.py template.yaml tests/test_mis_inscripciones.py
git commit -m "feat: endpoint GET /inscripciones?email= (mis inscripciones)"
```

### Task 3: Scaffolding Vite + React en `web/`

**Files:**
- Create: `web/package.json`, `web/vite.config.js`, `web/index.html`, `web/src/main.jsx`, `web/src/config.js`
- Move/delete: `web/index.html` actual pasa a `web/legacy-index.html` hasta el Task 4 (borrar al final)

**Interfaces:**
- Produces: `npm run build` genera `web/dist/` con `index.html` + assets; `web/src/config.js` exporta `API_URL` (constante string, placeholder hasta el deploy).

- [ ] **Step 1: Verificar toolchain**

Run: `node --version && npm --version`
Expected: Node ≥ 18. Si falta, instalar con `winget install OpenJS.NodeJS.LTS` y avisar.

- [ ] **Step 2: Crear el scaffold** (manual, sin `npm create` interactivo): `package.json` con `react`, `react-dom`, `vite`, `@vitejs/plugin-react`; `vite.config.js` con `base: './'` (importante para S3); `web/src/config.js` con `export const API_URL = "https://CAMBIAR-PEGA-AQUI";`

- [ ] **Step 3: Build de humo**

Run: `npm install && npm run build` (en `web/`)
Expected: `web/dist/index.html` generado sin errores.

- [ ] **Step 4: Commit**

```bash
git add web/
git commit -m "feat: scaffolding Vite + React del sitio"
```

### Task 4: UI pulida — eventos con cupos, formulario, mis inscripciones

**Files:**
- Create: `web/src/App.jsx`, `web/src/components/EventCard.jsx`, `web/src/components/SignupForm.jsx`, `web/src/components/MyRegistrations.jsx`, `web/src/styles.css`
- Modify: `web/index.html` (título, fuente)

**Interfaces:**
- Consumes: `API_URL` de `config.js`; contratos de Task 1 y Task 2.
- Produces: sitio que renderiza lista de eventos con "X/Y lugares", formulario validado, panel "Mis inscripciones" por email.

- [ ] **Step 1: Implementar componentes**

- `EventCard.jsx`: tarjeta con título, fecha (formateada `es-UY`), lugar, descripción, badge de cupos: `inscritos/cupo lugares` (color: verde >50%, ámbar ≤50%, rojo lleno). Props: `evento`, `onInscribirme(eventoId)`.
- `SignupForm.jsx`: select de evento (deshabilita los llenos), inputs nombre/email con validación inline (email regex, requeridos), estados: idle/enviando/éxito/error (mensaje del API en lenguaje humano).
- `MyRegistrations.jsx`: input de email → `GET /inscripciones?email=` → lista de inscripciones con título y fecha; estado vacío amable.
- `App.jsx`: carga `GET /eventos` al montar con estado cargando/error/listo; compone las tres secciones; refresca la lista tras inscribirse.
- `styles.css`: CSS moderno (custom properties, tipografía del sistema, tarjetas con sombra sutil, responsive a 1 columna en mobile).

- [ ] **Step 2: Build y verificación visual**

Run: `npm run build`
Luego abrir `web/dist/index.html` (o `npm run preview`) en el navegador y verificar con captura: lista carga, validación rechaza email inválido, cupos se muestran, la UI degrada bien con API inaccesible (error legible, no pantalla en blanco).

Expected: sin errores de build; captura que muestre las tres secciones.

- [ ] **Step 3: Commit**

```bash
git add web/
git commit -m "feat: UI React pulida (eventos, cupos, inscripcion, mis inscripciones)"
```

### Task 5: Documentación, dist y cierre

**Files:**
- Modify: `README.md` (estructura web/, instrucciones `npm run build`, deploy `aws s3 cp web/dist/`)
- Modify: `docs/Documento del proyecto.md` (alcance + flujo + demo con mis inscripciones y cupos; nota de seguridad del endpoint público)
- Delete: `web/legacy-index.html`

- [ ] **Step 1: Actualizar docs** según el contenido real de Tasks 1–4.

- [ ] **Step 2: Verificación final**

Run: `python -m unittest discover tests -v`
Expected: PASS (8/8). Y `npm run build` sin errores con `web/dist` actualizado.

- [ ] **Step 3: Commit y push**

```bash
git add -A
git commit -m "docs: sitio React, cupos y mis inscripciones"
git push
```
