# 04 · Tokens, scopes, permisos y límite de tasa

Este documento explica **las cuatro capas que deciden si una llamada a la API pasa**:

1. ¿El token es válido? → si no, `403 Invalid Token`
2. ¿El token tiene el scope que exige la ruta? → si no, `403 Insufficient scope`
3. ¿El usuario tiene el rol necesario en ese curso? → si no, `403` (o `404` si el recurso "no existe" para él)
4. ¿La app tiene créditos en el límite de tasa? → si no, `429`

(El límite de tasa en realidad se revisa primero, en el middleware; ver la sección 5.)

---

## 1. El access token

### Cómo es

Es un **JWT firmado con RS256** por la clave privada del mock (`data/signing_key.pem`). Ejemplo de
su contenido (decodificado):

**Encabezado**: `{"alg": "RS256", "kid": "3f9c1e0a7b2d4c51", "typ": "JWT"}`

**Claims**:

| Claim | Ejemplo | Significado |
|---|---|---|
| `nbf` | `1761100000` | No es válido antes de este momento |
| `exp` | `1761103600` | Vence en este momento (`nbf` + vida de la app) |
| `iss` | `https://api.brightspace.com/auth` | Quién lo emitió (copiado de un token real de ejemplo) |
| `aud` | `https://api.brightspace.com/auth/token` | Para quién es (copiado de un token real de ejemplo) |
| `sub` | `"3101"` | El usuario (o el usuario de servicio) |
| `tenantid` | `6c3d1a0e-...` | La institución (`TENANT_ID`) |
| `azp` | `b32dd75a-...` | La app (`client_id`) que lo pidió |
| `scope` | `"users:own_profile:read dropbox:folders:read"` | Permisos concedidos |
| `jti` | `9f1c...` | Identificador único del token |

Los claims imitan los de un token real de Brightspace que aparece como ejemplo en la documentación.

### Regla para tu cliente: el token es opaco

**EduTrace no debe leer ni validar el token de Brightspace.** Tómalo como un texto que solo se
copia en el encabezado `Authorization`. Razones:

- D2L no garantiza que su formato no cambie.
- No hay un JWKS público documentado de Brightspace con el que verificarlo.
- Para saber quién es el usuario está `whoami`; para saber cuándo vence, `expires_in`.

[MOCK] El mock publica su clave pública en `GET /.mock/jwks` solo para depurar. No existe en
Brightspace.

### Cómo lo verifica el mock (`verify_access_token`)

- Firma RS256 con la clave del mock. El algoritmo está **fijo** en el servidor: un token que diga
  `"alg": "none"` o HS256 se rechaza.
- `aud` e `iss` deben ser exactamente los de la tabla.
- Deben existir `exp`, `nbf`, `sub`, `azp` y `scope`.
- Sin tolerancia de reloj: vencido por un segundo = inválido.
- Después, en `current_caller`, el usuario de `sub` debe existir y estar **activo**.

Cualquier fallo → **`403` con el texto `Invalid Token`** [DOC]. Ojo: no es 401.

### De dónde se toma el token

Del encabezado `Authorization: Bearer <token>`. El mock también acepta
`Authentication: Bearer <token>` porque así aparece en un ejemplo de la documentación de OAuth de
D2L (probablemente una errata). **Usa `Authorization`**, que es el estándar (RFC 6750) y el que
usan las demás páginas de D2L. El prefijo `Bearer` no distingue mayúsculas.

### Cosas que conviene saber

- **No se puede revocar un access token**: vale hasta su `exp`. Si borras la app con
  `admin.py delete-app`, se borran sus códigos y refresh tokens, pero los access tokens ya
  emitidos siguen sirviendo hasta vencer, porque la verificación no consulta la base de apps.
- **Si cambias la clave** (borras `data/signing_key.pem` o haces `admin.py reset`), todos los
  tokens dejan de servir.
- **Si desactivas un usuario**, sus tokens dejan de servir de inmediato (se revisa en cada
  petición).

---

## 2. Scopes

### Gramática [DOC]

```
grupo:recurso:acción
```

- Varios scopes se separan con **espacios**: `users:own_profile:read dropbox:folders:read`
- Comodín en recurso o acción: `dropbox:*:read`, `users:userdata:*`
- Varias acciones con **comas sin espacios**: `dropbox:folders:read,write`
- El grupo **no** puede ser comodín. La excepción es el scope especial `core:*:*`.
- Partes válidas en el mock: minúsculas, dígitos y `_` (`[a-z0-9_]+`).

### Dos momentos en que se revisan

| Momento | Función | Pregunta | Error |
|---|---|---|---|
| Al pedir el token (`/oauth2/auth` o client credentials) | `is_subset(pedidos, registrados)` | ¿Cada scope pedido está cubierto por los registrados de la app? | `invalid_scope` |
| En cada llamada a la API | `satisfies(del_token, exigidos_por_la_ruta)` | ¿Algún scope del token cubre **alguno** de los que exige la ruta? | `403 Insufficient scope. Required: ...` |

"Cubrir" significa: mismo grupo, y el recurso es igual o `*`, y la acción está en la lista o es `*`.

Ejemplos con la ruta de carpetas, que exige `dropbox:folders:read`:

| Scope del token | ¿Pasa? | Por qué |
|---|---|---|
| `dropbox:folders:read` | Sí | Exacto |
| `dropbox:folders:read,write` | Sí | La lista incluye `read` |
| `dropbox:*:read` | Sí | Comodín de recurso |
| `dropbox:folders:*` | Sí | Comodín de acción |
| `dropbox:folders:write` | No | Falta `read` |
| `core:*:*` | **No** (por defecto) | Ver abajo |

El token lleva los scopes **que se pidieron**, no todos los registrados. Si registras muchos pero
pides pocos, el token solo tiene los pedidos.

### El caso `core:*:*`

La documentación de D2L lo describe como el scope de respaldo para **acciones que no tienen un
scope específico**. No queda claro si además abre las rutas que sí tienen scope propio. El mock es
**estricto** por defecto: `core:*:*` no sirve para ninguna de sus rutas (todas tienen scope
específico). Se puede cambiar con `CORE_SCOPE_GRANTS_ALL=true`.

Razón: si tu cliente pide los scopes específicos y funciona en modo estricto, funcionará también si
Brightspace resulta ser permisivo. Al revés no está garantizado.

### Scopes de cada ruta

Están en `05-REFERENCIA-API.md`. Todos salen de la tabla oficial de scopes de D2L.

---

## 3. Permisos por rol

El scope dice **qué tipo de operación** puede hacer la app. El rol dice **sobre qué cursos** puede
hacerla el usuario. Se necesitan ambos.

### Los roles del mock [APROX]

| Rol (tabla `roles`) | ID | `kind` | Dónde se usa |
|---|---|---|---|
| Instructor | 109 | `instructor` | Inscripción en un curso |
| Student | 110 | `student` | Inscripción en un curso |
| Administrator | 111 | `admin` | Rol de organización (`admin`) |
| Service User | 112 | `service` | Rol de organización (`svc_edutrace`) |
| User | 113 | `user` | Rol de organización de los demás usuarios |

Todos los usuarios tienen un **rol de organización** (`users.org_role_id`) y, además, un **rol en
cada curso** donde están inscritos (`enrollments.role_id`). En Brightspace también es así: alguien
puede ser docente en un curso y estudiante en otro.

### Cómo se decide (`course_role` y `require_course_role` en `deps.py`)

1. Si el curso no existe → **404** `Org unit not found`.
2. Si el usuario es **admin o servicio** a nivel de organización → rol `staff` (todos los cursos).
3. Si no, se busca su inscripción en ese curso → `instructor`, `student` o ninguno.
4. Cada ruta declara qué roles acepta:

| Conjunto | Incluye | Rutas típicas |
|---|---|---|
| `STAFF` | instructor del curso, staff | Crear/editar carpetas, ver entregas de todos, poner notas, publicar retroalimentación |
| `MEMBERS` | instructor, estudiante, staff | Ver carpetas, lista de clase, ítems de nota, descargar archivos (con filtro) |
| `STUDENT` | solo estudiante del curso | Entregar, ver *mis* entregas, ver *mis* notas |

Si el rol no está en el conjunto → **403** "The current user context does not have permission for
this action in this org unit."

### 403 vs 404: cuándo el mock "esconde" algo

Para no revelar que algo existe, algunas negativas son 404:

| Situación | Respuesta |
|---|---|
| Estudiante pide una carpeta **oculta** | 404 (para él no existe) |
| Estudiante pide un ítem de nota oculto | 404 |
| Estudiante intenta descargar el archivo de **otro** estudiante | 404 |
| Estudiante pide la retroalimentación **en borrador** de su propia entrega | 404 |
| Estudiante pide la retroalimentación de **otro** | 403 |
| Docente de otro curso pide cosas de este curso | 403 |

### Lo que cada rol ve distinto en la misma ruta

- **Carpetas**: el estudiante no ve las ocultas y los totales le llegan en `-1` [DOC: -1 cuando el
  llamador no tiene permiso para el conteo].
- **Lista de clase**: el estudiante recibe `Username`, `OrgDefinedId`, `Email`, `RoleId` y
  `LastAccessed` en `null` [APROX].
- **Notas**: el estudiante recibe `PrivateComments` vacío.
- **Usuarios** (`users/(userId)`): admin/servicio ven a todos; un docente ve a quien comparta un
  curso con él; cualquiera se ve a sí mismo. El resto → 403.

---

## 4. Las versiones en la ruta

Cada ruta lleva el producto y la versión: `/d2l/api/lp/1.49/...` (Learning Platform: usuarios,
inscripciones) o `/d2l/api/le/1.82/...` (Learning Environment: carpetas, notas, lista de clase).

- Versiones aceptadas por defecto [APROX]: `lp` 1.46–1.49, `le` 1.79–1.82. Configurables con
  `LP_VERSIONS` y `LE_VERSIONS`.
- Versión no soportada → **404** `Unsupported API version lp/1.20`.
- Las rutas de versiones (`/d2l/api/versions/`) son **anónimas** [DOC]: tu cliente puede
  consultarlas al arrancar para elegir una versión soportada en vez de tenerla fija.

---

## 5. Límite de tasa (token bucket)

### La idea [DOC]

Cada app tiene una **cubeta de créditos**. Cada llamada gasta créditos. La cubeta se va rellenando
con el tiempo. Si está vacía, la llamada se rechaza con **429** hasta que se rellene.

### Los números del mock [APROX: D2L no publica los suyos]

- Capacidad: `RATE_LIMIT_CAPACITY` = **300** créditos.
- Se rellena por completo en `RATE_LIMIT_WINDOW_S` = **60** segundos → 5 créditos por segundo.
- Cada llamada cuesta **1** crédito.

Ejemplo: haces 300 llamadas seguidas → la 301 recibe 429. Esperas 1 segundo → tienes 5 créditos.

### De quién es la cubeta

- Llamada con token válido → cubeta **de la app** (`azp`). Todos los usuarios de EduTrace comparten
  la misma cubeta, como en Brightspace, donde el límite es por aplicación.
- Llamada sin token o con token inválido → cubeta **de la IP** de origen.

### Encabezados en cada respuesta de `/d2l/api/...` [DOC]

| Encabezado | Significado |
|---|---|
| `X-Rate-Limit-Remaining` | Créditos que quedan después de esta llamada |
| `X-Request-Cost` | Cuánto costó esta llamada (siempre 1 en el mock) |
| `X-Rate-Limit-Reset` | Segundos hasta que la cubeta esté llena otra vez |
| `Retry-After` | Solo en el 429: cuántos segundos esperar |

Respuesta al agotarse: `429` con cuerpo `Too Many Requests`.

### Detalles

- La cubeta vive **en memoria**: reiniciar el mock la llena de nuevo.
- Las rutas de OAuth (`/oauth2/...`, `/core/connect/token`) **no** tienen límite de tasa en el mock.
- Detrás de un proxy o túnel, todas las peticiones sin token pueden parecer venir de la misma IP
  (la del proxy) y compartir cubeta.

### Qué debe hacer tu cliente

Leer `X-Rate-Limit-Remaining` y, ante un 429, esperar `Retry-After` segundos antes de reintentar,
sin reintentar en bucle inmediato.

---

## 6. Diagnóstico rápido de un 403

| Texto del 403 | Causa | Qué revisar |
|---|---|---|
| `Invalid Token` | Token ausente, mal copiado, sin `Bearer`, vencido, firmado con otra clave, o usuario desactivado | `expires_in`; si cambió la clave del mock; el encabezado |
| `Insufficient scope. Required: ...` | El token no tiene ese scope | Los scopes que **pediste** (no los registrados) |
| `The current user context does not have permission ...` | El usuario no tiene el rol necesario en ese curso | Si está inscrito y con qué rol (`admin.py users`) |
| `Not authorized to view this user` | `users/(userId)` de alguien con quien no compartes curso | — |
| `Only one submission is allowed in this folder.` | Carpeta con regla de una sola entrega | `SubmissionRule` de la carpeta |
| `The current user is not authorized to submit to this folder at this time.` | Carpeta fuera de su ventana de disponibilidad | `Availability` de la carpeta |
