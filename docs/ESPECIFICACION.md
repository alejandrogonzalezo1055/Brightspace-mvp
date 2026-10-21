# Mock de Brightspace — Especificación

Este documento dice **qué copia el mock de Brightspace real y qué aproxima**. Todo lo marcado como
**[DOC]** sale de la documentación oficial de D2L (consultada el 21-oct-2026). Lo marcado como
**[APROX]** no está documentado públicamente o la documentación es ambigua: el mock elige un
comportamiento razonable y lo deja configurable cuando se puede.

Regla para EduTrace: **si el cliente funciona contra el mock en modo estricto, debería funcionar
contra Brightspace real**. Lo contrario no está garantizado en los puntos [APROX].

---

## 1. Hosts

| En Brightspace real | En el mock |
|---|---|
| Servidor de autorización: `https://auth.brightspace.com` [DOC] | `AUTH_BASE_URL` (por defecto el mismo host del mock) |
| API de la institución: `https://<institución>.brightspace.com` [DOC] | `API_BASE_URL` (por defecto el mismo host del mock) |

El cliente de EduTrace debe tener **dos URL configurables** (autorización y API), igual que en real.

## 2. OAuth 2.0

### 2.1 Endpoints [DOC]
- Autorización: `GET /oauth2/auth`
- Token: `POST /core/connect/token`

### 2.2 Authorization Code Grant
| Aspecto | Comportamiento | Origen |
|---|---|---|
| Parámetros de `/oauth2/auth` | `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state` | [APROX] D2L remite al estándar OAuth 2 (RFC 6749 §4.1) |
| `redirect_uri` | Debe coincidir **exactamente** con la registrada | [APROX] fuentes de terceros dicen que Brightspace es estricto; RFC lo recomienda |
| `client_id` o `redirect_uri` inválidos | Página de error, **sin** redirigir | [APROX] RFC 6749 §4.1.2.1 |
| Otros errores (scope no registrado, `response_type` malo, usuario niega) | Redirige a `redirect_uri?error=...&state=...` | [APROX] RFC 6749 §4.1.2.1 |
| Scopes pedidos | Deben ser subconjunto de los registrados | [DOC] |
| Consentimiento | Opcional por app ("Prompt for user consent"); se recuerda indefinidamente hasta revocarlo | [DOC] |
| Código de autorización | Un solo uso, vence a los 5 minutos | [APROX] |
| Autenticación del cliente en `/core/connect/token` | HTTP Basic (`client_id:client_secret`) **o** `client_id`/`client_secret` en el cuerpo | [DOC] Postman usa Basic; desde 2019 se acepta `client_id` como parámetro |
| Content-Type del token | `application/x-www-form-urlencoded` | [DOC] |
| Respuesta del token | `access_token`, `token_type: "Bearer"`, `expires_in`, `scope`, `refresh_token` (si la app lo tiene habilitado) | [APROX] campos del RFC 6749 §5.1; D2L no los documenta |
| Errores del token | JSON `{"error": "invalid_grant" \| "invalid_client" \| ...}` con 400/401 | [APROX] RFC 6749 §5.2 |
| Vida del access token | La registrada, entre 1800 y 72000 s; el cliente debe leer `expires_in` | [DOC] |
| Refresh token | **Un solo uso**: cada canje entrega un par nuevo y el viejo deja de servir | [DOC] |
| PKCE | No soportado (D2L no lo menciona) | [APROX] |

### 2.3 Client Credentials Grant (servidor a servidor) [DOC]
- Cuerpo: `grant_type=client_credentials`,
  `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`,
  `client_assertion=<JWT>`, `scope=...`.
- El JWT del cliente:
  - encabezado `alg` ∈ {RS256, RS384, RS512, ES256, ES384, ES512} y `kid`;
  - claims `aud` = URL del endpoint de token, `iss` = `sub` = client_id, `iat`, `exp`, `jti`;
  - vida recomendada ≤ 60 s, máxima 5 min (el mock rechaza > 5 min);
  - `jti` de un solo uso (el mock rechaza repetidos).
- Brightspace descarga las claves públicas desde la **URL JWKS (HTTPS)** registrada.
  El mock acepta también `http://` y `file://` para pruebas locales.
- El token resultante actúa como el **usuario de servicio** asociado a la app.
- No emite refresh token.

### 2.4 Access token
- Es un JWT firmado RS256 por el mock. Claims copiados de un token real de ejemplo:
  `iss=https://api.brightspace.com/auth`, `aud=https://api.brightspace.com/auth/token`,
  `sub` (UserId), `tenantid`, `azp` (client_id), `scope`, `jti`, `nbf`, `exp`.
  **[APROX]**: el cliente debe tratarlo como opaco; no debe depender de su contenido.
- Clave pública del mock en `GET /.mock/jwks` (**solo existe en el mock**).

## 3. Llamadas a la API

| Aspecto | Comportamiento | Origen |
|---|---|---|
| Encabezado | `Authorization: Bearer <token>`. También acepta `Authentication: Bearer` (así aparece en un ejemplo de la doc de OAuth) | [DOC] |
| Sin token / token inválido / vencido | **403** con cuerpo texto `Invalid Token` (no 401) | [DOC] |
| Falta scope | 403 | [DOC] |
| Sin permiso por rol | 403 | [DOC] |
| Recurso inexistente | 404 (cuerpo puede venir vacío) | [DOC] |
| Método no soportado | 405 | [DOC] |
| Content-Type equivocado | 415 | [DOC] |
| JSON inválido | 400 | [DOC] |
| Formato del cuerpo de error | Texto plano; D2L **no define un esquema JSON de error** | [DOC] |
| Versión no soportada en la ruta | 404 | [APROX] |
| Rutas | Mayúsculas/minúsculas y barra final tal cual las documenta D2L | [APROX] |

### 3.1 Límite de tasa (token bucket) [DOC] + valores [APROX]
Encabezados en cada respuesta de la API: `X-Rate-Limit-Remaining`, `X-Request-Cost`,
`X-Rate-Limit-Reset`; al agotarse: **429** + `Retry-After`. D2L no publica tamaños de cubeta ni
costos: el mock usa 1 crédito por llamada y una cubeta configurable (`RATE_LIMIT_CAPACITY`,
`RATE_LIMIT_WINDOW_S`).

### 3.2 Convenciones [DOC]
- Fechas `UTCDateTime`: `yyyy-MM-ddTHH:mm:ss.fffZ`.
- `RichText` (salida): `{"Text": ..., "Html": ...}`. `RichTextInput` (entrada): `{"Content": ..., "Type": "Text"|"Html"}`.
- `D2LID`: entero de 64 bits; a veces viaja como string (p. ej. `Identifier` en whoami).
- Paginación **[APROX: estructura tomada de conocimiento previo, no la pude verificar en la doc]**:
  - `Api.PagedResultSet`: `{"PagingInfo": {"Bookmark": "...", "HasMoreItems": bool}, "Items": [...]}`
    — siguiente página con `?bookmark=`.
  - `Api.ObjectListPage`: `{"Next": "<URL>" | null, "Objects": [...]}`.

## 4. Rutas implementadas

Versiones anunciadas por el mock **[APROX: D2L no publica la última versión; configurable]**:
`lp`: 1.46–1.49, `le`: 1.79–1.82.

| Ruta | Scope [DOC] | Devuelve [DOC] |
|---|---|---|
| `GET /d2l/api/versions/` | anónima | lista de `ProductVersions` |
| `GET /d2l/api/(product)/versions/` | anónima | `ProductVersions` |
| `GET /d2l/api/(product)/versions/(version)` | anónima | `SupportedVersion` |
| `POST /d2l/api/versions/check` | anónima | `BulkSupportedVersionResponse` |
| `GET /d2l/api/lp/(v)/users/whoami` | `users:profile:read` o `users:own_profile:read` | `WhoAmIUser` |
| `GET /d2l/api/lp/(v)/users/(userId)` | `users:userdata:read` | `UserData` |
| `GET /d2l/api/lp/(v)/enrollments/myenrollments/` | `enrollment:own_enrollment:read` | PagedResultSet de `MyOrgUnitInfo` |
| `GET /d2l/api/lp/(v)/enrollments/orgUnits/(ou)/users/` | `enrollment:orgunit:read` | PagedResultSet de `OrgUnitUser` |
| `GET /d2l/api/le/(v)/(ou)/classlist/` | `enrollment:orgunit:read` | arreglo de `ClasslistUser` |
| `GET /d2l/api/le/(v)/(ou)/classlist/paged/` | `enrollment:orgunit:read` | ObjectListPage de `ClasslistUser` |
| `GET /d2l/api/le/(v)/(ou)/dropbox/folders/` | `dropbox:folders:read` | arreglo de `DropboxFolder` |
| `GET /d2l/api/le/(v)/(ou)/dropbox/folders/(f)` | `dropbox:folders:read` | `DropboxFolder` |
| `POST /d2l/api/le/(v)/(ou)/dropbox/folders/` | `dropbox:folders:write` | `DropboxFolder` |
| `PUT /d2l/api/le/(v)/(ou)/dropbox/folders/(f)` | `dropbox:folders:write` | `DropboxFolder` |
| `GET .../folders/(f)/submissions/` | `dropbox:folders:read` | arreglo de `EntityDropbox` |
| `GET .../folders/(f)/submissions/paged/` | `dropbox:folders:read` | ObjectListPage de `EntityDropbox` |
| `GET .../folders/(f)/submissions/mysubmissions/` | `dropbox:folders:read` | arreglo de `EntityDropbox` [APROX forma] |
| `POST .../folders/(f)/submissions/mysubmissions/` | `dropbox:folders:write` | 200 sin cuerpo; `multipart/mixed` |
| `GET .../folders/(f)/submissions/user/(userId)` | `dropbox:folders:read` | arreglo de `EntityDropbox` [APROX forma] |
| `GET .../folders/(f)/submissions/(s)/files/(file)` | `dropbox:folders:read` | binario del archivo |
| `GET .../folders/(f)/feedback/(user\|group)/(id)` | `dropbox:folders:read` | `DropboxFeedbackOut` |
| `POST .../folders/(f)/feedback/(user\|group)/(id)` | `dropbox:folders:write` | 200 sin cuerpo |
| `GET /d2l/api/le/(v)/(ou)/grades/` | `grades:gradeobjects:read` | arreglo de `GradeObject` |
| `GET /d2l/api/le/(v)/(ou)/grades/(g)` | `grades:gradeobjects:read` | `GradeObject` |
| `GET .../grades/(g)/values/` | `grades:gradevalues:read` | ObjectListPage de `UserGradeValue` |
| `GET .../grades/(g)/values/(userId)` | `grades:gradevalues:read` | `GradeValue` |
| `PUT .../grades/(g)/values/(userId)` | `grades:gradevalues:write` | 200 sin cuerpo [APROX] |
| `GET .../grades/(g)/values/myGradeValue` | `grades:own_grades:read` | `GradeValue` |
| `GET /d2l/api/le/(v)/(ou)/grades/values/myGradeValues/` | `grades:own_grades:read` | arreglo de `GradeValue` |
| `GET /d2l/api/le/(v)/(ou)/grades/final/values/myGradeValue` | `grades:own_grades:read` | `GradeValue` final [APROX cálculo] |

`multipart/mixed` de una entrega [DOC]: primera parte `application/json` con un `RichText`
(comentario), luego el archivo con `Content-Disposition` que lleva `filename` y `name` vacío.
**El archivo es obligatorio.** Límites: JSON 1 MB, binario 490 MB (configurables en el mock).

## 5. Permisos por rol [APROX]

En Brightspace los permisos los configura cada institución por rol. El mock usa una
configuración típica:

| Acción | Instructor del curso | Estudiante del curso | Usuario de servicio |
|---|---|---|---|
| Ver carpetas, lista de clase | sí | sí (lista de clase sin correo) | sí |
| Crear/editar carpetas | sí | no | sí |
| Ver entregas de todos | sí | no (solo `mysubmissions`) | sí |
| Entregar | no | sí, si la carpeta está disponible | no |
| Publicar retroalimentación | sí | no | sí |
| Ver/poner notas de otros | sí | no | sí |
| Ver notas propias | — | sí (solo las publicadas) | — |

Fuera del curso: 403.

## 6. Comportamientos de dominio [APROX]
- Publicar retroalimentación con `IsGraded: true` y `Score` en una carpeta enlazada a un ítem de
  calificación (`GradeItemId`) **copia la nota al libro de calificaciones**. Así funciona la
  interfaz de Brightspace; el detalle exacto por API no está documentado.
- El estudiante solo ve retroalimentación y notas publicadas (`IsGraded: true` / `ReleasedDate`).
- Nota final = suma de puntos obtenidos / suma de puntos máximos de los ítems numéricos con nota.

## 7. Fuera del alcance
LTI 1.3, carga resumible, archivos adjuntos en retroalimentación, rúbricas, grupos, quizzes,
contenido, analíticas, logs, revocación de tokens, autenticación legacy ID-Key.
