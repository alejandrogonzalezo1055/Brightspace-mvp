# 09 · Fidelidad: qué es copia de D2L y qué no

El mock solo es útil si sabes **en qué puedes confiar**. Este documento junta en un solo lugar
todo lo que es copia de la documentación oficial ([DOC]), lo que es aproximación ([APROX]), lo que
solo existe en el mock ([MOCK]) y lo que falta.

La documentación de D2L se consultó en octubre de 2026 (fuentes al final). Brightspace puede
cambiar: si algo de [DOC] no cuadra con el Brightspace real, gana el real.

## 1. Cómo usar esta tabla

- **[DOC]**: puedes programar contra eso con confianza razonable.
- **[APROX]**: tu código **no debe depender** de ese detalle exacto. Prográmalo de forma tolerante
  (por ejemplo, no asumas un valor fijo) y verifícalo cuando haya acceso a Brightspace real.
- **[MOCK]**: no existe en Brightspace; no lo uses desde EduTrace.

## 2. OAuth 2.0

| Comportamiento | Fidelidad | Nota |
|---|---|---|
| URL de autorización `/oauth2/auth` y de token `/core/connect/token` | DOC | En real están en `auth.brightspace.com` |
| Concesiones Authorization Code y Client Credentials | DOC | |
| Parámetros `response_type`, `client_id`, `redirect_uri`, `scope`, `state` | APROX | D2L remite al estándar OAuth 2 |
| `redirect_uri` con coincidencia exacta | APROX | Fuentes de terceros dicen que Brightspace es estricto; el RFC lo recomienda |
| Errores de autorización por redirección (`?error=...`) y página sin redirigir para cliente/URI inválidos | APROX | RFC 6749 §4.1.2.1 |
| Scope obligatorio en la autorización | APROX | El mock es más estricto que el estándar |
| Scopes pedidos ⊆ scopes registrados | DOC | |
| Consentimiento opcional por app y recordado indefinidamente | DOC | |
| Página de login y consentimiento | MOCK | Diseño propio; no imita la de D2L |
| Código de un uso, vida de 5 minutos | APROX | Un uso es estándar; la vida no está documentada |
| Autenticación del cliente con HTTP Basic | DOC | Así lo configura la guía de Postman de D2L |
| Autenticación del cliente con `client_id`/`client_secret` en el cuerpo | APROX | D2L menciona que acepta `client_id` como parámetro |
| Cuerpo del token en `x-www-form-urlencoded` | DOC | |
| Campos de la respuesta del token | APROX | RFC 6749 §5.1; D2L no los documenta |
| Errores del endpoint de token en JSON (`invalid_grant`, …) | APROX | RFC 6749 §5.2 |
| Vida del access token entre 1800 y 72000 s, leída de `expires_in` | DOC | |
| Refresh token de un solo uso con rotación | DOC | |
| Vida del refresh token (30 días) | APROX | No documentada |
| No revocar la cadena al reusar un refresh token | APROX | No documentado |
| `client_assertion_type` jwt-bearer y los campos de la petición | DOC | |
| Algoritmos RS/ES 256/384/512, `kid`, claims `aud` `iss` `sub` `iat` `exp` `jti` | DOC | |
| Aserción de vida máxima 5 minutos y `jti` de un solo uso | DOC | |
| JWKS por HTTPS | DOC | El mock acepta http/file mientras `ALLOW_INSECURE_JWKS=true` [MOCK] |
| Sin caché del JWKS | MOCK | |
| Token de servidor a servidor actúa como usuario de servicio | DOC | |
| PKCE | — | No documentado por D2L; el mock lo ignora |
| OpenID Connect (`id_token`, *userinfo*) | — | No documentado por D2L; no existe en el mock |

## 3. Tokens y llamadas a la API

| Comportamiento | Fidelidad | Nota |
|---|---|---|
| `Authorization: Bearer <token>` | DOC | |
| También `Authentication: Bearer` | DOC (dudoso) | Aparece en un ejemplo de D2L; probablemente errata. Usa `Authorization` |
| Token como JWT con `iss`, `aud`, `sub`, `tenantid`, `azp`, `scope`, `jti` | APROX | Copiado de un token de ejemplo; trátalo como opaco |
| Token inválido o vencido → 403 `Invalid Token` | DOC | |
| Scope insuficiente → 403 | DOC | El texto exacto del mock es propio |
| Rol insuficiente → 403; recurso inexistente → 404 | DOC | Los textos son propios |
| Parámetro de ruta que no se puede interpretar → 404 | DOC | |
| Método no soportado → 405; tipo de contenido → 415; JSON inválido → 400 | DOC | |
| Errores en texto plano, sin esquema JSON | DOC | |
| Límite de tasa con token bucket y sus 4 encabezados; 429 | DOC | |
| Capacidad, ventana y costo por llamada | APROX | D2L no los publica |
| Límite de tasa por app (y por IP sin token) | APROX | |
| Versión no soportada → 404 | APROX | |
| Versiones `lp` 1.46–1.49 y `le` 1.79–1.82 | APROX | D2L no publica cuál es la última; consúltala con `/d2l/api/versions/` |
| Rutas de versiones anónimas | DOC | |
| Barra final estricta | APROX | Las rutas se escribieron tal como las documenta D2L |
| Formato de fecha `yyyy-MM-ddTHH:mm:ss.fffZ` | DOC | |
| `RichText` (salida) y `RichTextInput` (entrada) | DOC | El mock también acepta `RichText` de entrada (tolerancia) |

## 4. Rutas y estructuras

| Elemento | Fidelidad | Nota |
|---|---|---|
| Todas las rutas implementadas y sus scopes | DOC | Tabla oficial de scopes |
| `WhoAmIUser`, `UserData` | DOC | `LastAccessedDate` y `FirstLoginDate` son de relleno [MOCK] |
| `User.User` (dentro de `OrgUnitUser` y `UserGradeValue`) | APROX | Forma de conocimiento previo |
| `MyOrgUnitInfo`, `OrgUnitInfo`, `RoleInfo`, `ClasslistUser` | DOC | `HomeUrl`, `LISRoles`, `CanAccess` aproximados |
| `Api.PagedResultSet` y `Api.ObjectListPage` | APROX | Forma de conocimiento previo, no verificada |
| `myenrollments` solo con cursos (sin organización ni departamentos) | APROX | |
| `DropboxFolder` y `DropboxFolderUpdateData` | DOC | `ActivityId`, adjuntos y valores de `SubmissionRule` aproximados |
| Totales en −1 para quien no puede verlos | DOC | |
| `PUT` parcial: `null` o ausente conserva el valor | DOC | |
| `EntityDropbox`, `Entity`, archivos con `isRead`/`isFlagged` | DOC | |
| Valores de `Status` (0–3), `SubmissionType`, `DropboxType`, `CompletionType` | DOC | |
| Cálculo de `Status` | APROX | |
| `submissions/` devuelve un elemento por cada estudiante activo | APROX | |
| Forma de la respuesta de `mysubmissions` y `submissions/user/(id)` | APROX | |
| Entrega `multipart/mixed` con JSON primero y archivo obligatorio; 200 sin cuerpo | DOC | |
| Límites 1 MB (JSON) y ~490 MB (binario) | DOC | El mock usa 50 MB por defecto |
| `DropboxFeedback` / `DropboxFeedbackOut` | DOC | |
| Publicar con nota pasa el puntaje al libro | APROX | Comportamiento de la interfaz web; no documentado por API |
| Fórmula de conversión de puntaje a puntos | APROX | |
| `GradeObject` y `GradeValue` numéricos, `IncomingGradeValue` | DOC | `DisplayedGrade`, `GradeSchemeUrl`, `AssociatedTool` aproximados |
| `PUT` de nota responde 200 sin cuerpo y publica de inmediato | APROX | |
| Cálculo de la nota final | APROX | |
| Permisos por rol (qué ve y hace cada rol) | APROX | En Brightspace los configura cada institución |
| IDs de roles, tipos de unidad y datos de demo | APROX | Inventados: descúbrelos por API |

## 5. Lo que no existe en el mock

LTI 1.3 · carga resumible · adjuntos en retroalimentación y carpetas · rúbricas · `GradedSymbol` ·
grupos y entregas grupales · entregas de solo texto · `markAsRead` y banderas · categorías de
carpetas · crear o editar ítems de calificación · esquemas de calificación · contenido, quizzes,
anuncios · revocación de tokens · autenticación antigua por ID-Key · registro de accesos
(`LastAccessed`).

## 6. Lo primero que habría que verificar en Brightspace real

Si algún día hay acceso a una instancia (sandbox de D2L o la de la universidad), estas son las
aproximaciones que más afectarían a EduTrace, en orden:

1. Forma exacta de la paginación (`PagedResultSet` y `ObjectListPage`).
2. Si publicar retroalimentación con puntaje por API pasa la nota al libro.
3. Campos de la respuesta del token y formato de sus errores.
4. Si `core:*:*` abre rutas con scope específico.
5. La versión más reciente de `lp` y `le`.
6. El encabezado `Authorization` vs `Authentication`.
7. Si se acepta PKCE.

## 7. Fuentes consultadas

- OAuth 2.0: https://docs.valence.desire2learn.com/basic/oauth2.html
- Convenciones de llamada: https://docs.valence.desire2learn.com/basic/apicall.html
- Convenciones de tipos: https://docs.valence.desire2learn.com/basic/conventions.html
- Carga de archivos: https://docs.valence.desire2learn.com/basic/fileupload.html
- Versiones: https://docs.valence.desire2learn.com/res/apiprop.html
- Usuarios: https://docs.valence.desire2learn.com/res/user.html
- Inscripciones: https://docs.valence.desire2learn.com/res/enroll.html
- Carpetas de entrega: https://docs.valence.desire2learn.com/res/dropbox.html
- Calificaciones: https://docs.valence.desire2learn.com/res/grade.html
- Tabla de scopes: https://docs.valence.desire2learn.com/http-scopestable.html
- Postman con la API de Brightspace: https://community.d2l.com/brightspace/kb/articles/1100-using-postman-with-the-brightspace-api
- Registro de apps servidor a servidor: https://community.d2l.com/brightspace/kb/articles/33526-register-an-oauth2-0-application-for-server-to-server-authentication
- Pruebas de integraciones LTI (fuente de terceros): https://docs.ltiaas.com/learn/testing-lti-integrations
- RFC 6749 (OAuth 2.0), RFC 6750 (Bearer), RFC 7521/7523 (aserciones JWT), RFC 7519 (JWT), RFC 2046 (multipart)
