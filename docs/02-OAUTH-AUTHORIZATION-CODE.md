# 02 · OAuth 2.0: Authorization Code (login con usuario)

Este es el flujo que EduTrace usará para que un docente o estudiante "entre con Brightspace". Aquí
se explica cada paso, qué manda cada parte, **qué valida el mock y en qué función**, y por qué.

Archivos: `app/oauth/routes.py` (HTTP), `app/oauth/service.py` (lógica), `app/oauth/pages.py`
(HTML), `app/security/tokens.py` (access token), `app/apps.py` (registro de la app).

---

## 1. Primero: qué es OAuth aquí (y qué no)

OAuth 2.0 es **autorización delegada**: el usuario le da permiso a una aplicación (EduTrace) para
usar *su* cuenta de Brightspace con ciertos permisos (scopes), **sin darle su contraseña**.
EduTrace nunca ve la contraseña de Brightspace: el usuario la escribe en la página de Brightspace,
y EduTrace solo recibe un **access token**.

Los cuatro actores:

| Actor | Quién es en EduTrace |
|---|---|
| **Usuario** (resource owner) | El docente o estudiante |
| **Navegador** (user agent) | El navegador del usuario: lleva y trae redirecciones |
| **Cliente** | El backend de EduTrace (tu servicio en Python) |
| **Servidor de autorización + API** | Brightspace (o el mock) |

Dos canales:

- **Canal del navegador (front-channel)**: redirecciones que pasan por el navegador. Todo lo que
  viaja por aquí es visible y manipulable por el usuario o por un atacante. Por eso por aquí solo
  viaja el **código**, que solo sirve una vez, vence pronto y no sirve sin el secreto de la app.
- **Canal de servidor a servidor (back-channel)**: EduTrace habla directo con Brightspace. Aquí
  viajan el **secreto de la app** y los **tokens**.

---

## 2. Antes de todo: registrar la app

En Brightspace, un administrador registra EduTrace en *Manage Extensibility > OAuth 2.0*. En el
mock se hace con `admin.py register-app`, que llama a `register_authorization_code_app` en
`app/apps.py`. Lo que se guarda (tabla `oauth_clients`):

| Dato | Para qué | Validación al registrar |
|---|---|---|
| `client_id` (UUID aleatorio) | Identifica a la app. Es público | — |
| `client_secret` | Prueba que quien canjea el código es la app de verdad. **Solo se muestra una vez**; en la base queda su hash PBKDF2 | — |
| `redirect_uri` | A dónde devolver al usuario con el código | Debe empezar por `http://` o `https://` |
| `scopes` | Máximo de permisos que la app puede pedir | Formato válido (`grupo:recurso:acción`) |
| `token_lifetime` | Vida del access token en segundos | Entre 1800 y 72000 [DOC] |
| `refresh_enabled` | Si se emiten refresh tokens (por defecto sí; `--no-refresh` lo apaga) | — |
| `prompt_consent` | Si se le pide al usuario autorizar la app (por defecto sí; `--no-consent` lo apaga) | — |

---

## 3. El flujo completo

```mermaid
sequenceDiagram
    autonumber
    participant U as Usuario + navegador
    participant E as EduTrace (backend)
    participant A as Mock: autorización
    participant API as Mock: API

    U->>E: "Entrar con Brightspace"
    E->>E: genera state aleatorio y lo guarda en la sesión del usuario en EduTrace
    E-->>U: 302 → /oauth2/auth?response_type=code&client_id&redirect_uri&scope&state
    U->>A: GET /oauth2/auth?...
    A->>A: valida client_id, redirect_uri, response_type, scope
    A-->>U: página de login (si no hay sesión del mock)
    U->>A: POST /oauth2/auth/login (usuario, contraseña, csrf)
    A-->>U: página de consentimiento (si la app la exige y aún no se dio)
    U->>A: POST /oauth2/auth/consent (allow)
    A-->>U: 302 → redirect_uri?code=...&state=...
    U->>E: GET /callback?code&state
    E->>E: compara state con el guardado (si no coincide: rechazar)
    E->>A: POST /core/connect/token (Basic client_id:secret; grant_type=authorization_code, code, redirect_uri)
    A-->>E: { access_token, token_type, expires_in, scope, refresh_token }
    E->>API: GET /d2l/api/lp/1.49/users/whoami (Authorization: Bearer ...)
    API-->>E: { Identifier, FirstName, UniqueName, ... }
    E-->>U: sesión de EduTrace iniciada
```

Pasos 1–3, 13 y 16 son **tu código** en EduTrace. El resto lo hace el mock (o Brightspace).

---

## 4. Paso a paso con lo que valida el mock

### Paso 3–5: `GET /oauth2/auth`

Lo que EduTrace pone en la URL (como query string):

| Parámetro | Obligatorio | Qué es |
|---|---|---|
| `response_type` | sí | Siempre `code` |
| `client_id` | sí | El de la app registrada |
| `redirect_uri` | sí | **Exactamente** la registrada |
| `scope` | sí (en el mock) | Scopes separados por espacio (en la URL, `%20`) |
| `state` | recomendado | Valor aleatorio que EduTrace genera y luego compara |

La función `validate_authorization_request` revisa, en este orden:

| # | Chequeo | Si falla | Por qué así |
|---|---|---|---|
| 1 | `client_id` existe y la app es de tipo Authorization Code | **Página de error 400, sin redirigir** | Si la app no existe, no hay una `redirect_uri` confiable a la cual mandar el error |
| 2 | `redirect_uri` es **idéntica** a la registrada (ni una barra de más) | **Página de error 400, sin redirigir** | Si se redirigiera a una URI no registrada, un atacante podría hacer que el código llegue a su servidor |
| 3 | `response_type == code` | Redirige con `error=unsupported_response_type` | A partir de aquí la `redirect_uri` ya es confiable, así que los errores se le devuelven a la app (RFC 6749 §4.1.2.1) |
| 4 | Hay `scope` | Redirige con `error=invalid_scope` | [APROX] el estándar permite un scope por defecto; el mock lo exige para ser estricto |
| 5 | Los scopes pedidos tienen formato válido y son **subconjunto** de los registrados | Redirige con `error=invalid_scope` | [DOC] |

Los errores redirigidos llegan así a tu callback:
`redirect_uri?error=invalid_scope&error_description=...&state=...`. **Tu callback tiene que mirar
`error` antes que `code`.**

Si todo está bien:

- Si el navegador **no tiene sesión en el mock** (cookie `d2lSessionVal`), se muestra el login.
- Si **ya tiene sesión** y la app no necesita consentimiento (o ya se dio), el mock emite el código
  de una vez y redirige. Por eso la segunda vez que pruebas el flujo no ves ni login ni
  consentimiento.

### Paso 6: `POST /oauth2/auth/login`

El formulario lleva el usuario, la contraseña, la query original (campo oculto `request`) y un
token anti-CSRF (campo oculto `csrf`).

1. **Anti-CSRF de doble envío**: al mostrar el login, el mock pone un valor aleatorio en la cookie
   `mock_login_csrf` y el mismo valor en el campo oculto. Al recibir el formulario compara ambos.
   Una página maliciosa podría enviar el formulario, pero no puede leer ni poner esa cookie, así
   que no puede hacer coincidir los valores. Si no coinciden: el login vuelve a mostrarse con
   error 400.
2. **Revalida toda la solicitud** (`validate_authorization_request` otra vez): el campo `request`
   viene del navegador, así que no se confía en que siga siendo válido.
3. **Autentica** (`authenticate_user`): usuario activo + contraseña verificada con PBKDF2 en tiempo
   constante. Si falla: login otra vez con **401** "Usuario o contraseña incorrectos".
4. **Crea la sesión del navegador** (`create_login_session`): un identificador aleatorio en la
   cookie `d2lSessionVal` (HttpOnly, SameSite=Lax, 8 horas); en la base se guarda su hash y un
   `csrf_token` propio de esa sesión (para el consentimiento).
5. Sigue con el consentimiento o con el código.

> Esta sesión es **del mock** (como la sesión de Brightspace en tu navegador), no de EduTrace.
> Cerrarla: `GET /d2l/logout`.

### Paso 7–8: consentimiento (`POST /oauth2/auth/consent`)

Se muestra si la app tiene `prompt_consent` y el usuario no la ha autorizado antes
(`needs_consent`). La página lista los scopes pedidos.

- El formulario lleva el `csrf_token` **de la sesión** (no una cookie aparte): si no coincide, error.
- `Permitir` → se guarda el consentimiento (tabla `oauth_consents`) y se emite el código. El
  consentimiento queda **recordado indefinidamente** [DOC]: la próxima vez no se pregunta.
- `Cancelar` → redirige con `error=access_denied` y el `state`.

### Paso 9: el código

`issue_code_redirect` genera un código aleatorio (32 bytes, base64url) y guarda en
`oauth_codes`: su hash, la app, el usuario, la `redirect_uri`, los scopes y la expiración
(**5 minutos** [APROX]). Redirige a `redirect_uri?code=...&state=...` (sin `state` si no vino).

### Paso 11: comparar el `state` (lo hace EduTrace, no el mock)

El mock **solo devuelve** el `state` que recibió. Comprobar que coincide con el que EduTrace
guardó es responsabilidad tuya. Sin esa comparación, un atacante podría hacer que un usuario
termine logueado en EduTrace con la cuenta del atacante (CSRF de login).

### Paso 12–13: `POST /core/connect/token` con `grant_type=authorization_code`

**Formato obligatorio**: `Content-Type: application/x-www-form-urlencoded` [DOC]. Si mandas JSON:
`400 invalid_request`.

**Autenticación de la app** (`_client_from_basic_or_body`), una de dos formas:

| Forma | Cómo |
|---|---|
| HTTP Basic (la que usa la guía de Postman de D2L) | Encabezado `Authorization: Basic base64(client_id:client_secret)` |
| En el cuerpo | Campos `client_id` y `client_secret` en el formulario |

Reglas: no se pueden usar ambas para el secreto a la vez (`invalid_request`); si mandas Basic y
además `client_id` en el cuerpo, deben ser iguales. Secreto incorrecto o app inexistente:
**401 `invalid_client`** con `WWW-Authenticate: Basic`.

**Cuerpo:**

| Campo | Valor |
|---|---|
| `grant_type` | `authorization_code` |
| `code` | El que llegó al callback |
| `redirect_uri` | **La misma** que se usó en el paso 3 |

Lo que valida `exchange_code`:

| Chequeo | Error |
|---|---|
| El código existe y es de **esta** app | `400 invalid_grant` |
| No se ha usado | `400 invalid_grant` ("ya se usó") |
| No venció (5 min) | `400 invalid_grant` |
| `redirect_uri` igual a la del paso 3 | `400 invalid_grant` |

Si todo pasa, marca el código como usado y responde:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "users:own_profile:read enrollment:own_enrollment:read",
  "refresh_token": "kq3...Zt"
}
```

- `expires_in` es la vida registrada para la app. **Léelo siempre**: D2L advierte que la vida
  real puede no ser la que pediste.
- `refresh_token` solo aparece si la app lo tiene habilitado.
- [APROX] D2L no documenta los campos de esta respuesta; son los del estándar (RFC 6749 §5.1).

> **Error típico en desarrollo**: recargar la página del callback vuelve a canjear el mismo código
> → `invalid_grant`. El código es de un solo uso.

### Paso 14–15: usar el token

Toda llamada a `/d2l/api/...` lleva `Authorization: Bearer <access_token>`. Ver
`04-TOKENS-SCOPES-PERMISOS.md` para lo que pasa al verificarlo.

La identidad del usuario se obtiene con `GET /d2l/api/lp/(version)/users/whoami`. Brightspace no
documenta OpenID Connect (no hay `id_token` ni endpoint *userinfo*), así que **`whoami` es la
forma de saber quién inició sesión**. Es confiable porque el token llegó por el canal de servidor a
servidor, en respuesta al canje del código.

---

## 5. Refresh tokens (de un solo uso)

Cuando el access token vence, EduTrace no debe mandar al usuario a loguearse otra vez: usa el
refresh token.

```http
POST /core/connect/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=kq3...Zt
```

Lo que hace `exchange_refresh_token`:

1. Autentica a la app igual que en el canje del código.
2. Si la app no tiene refresh habilitado: `400 unauthorized_client`.
3. Busca el refresh token (por su hash). Debe ser de esta app, **no usado** y no vencido
   (30 días por defecto [APROX], variable `REFRESH_TOKEN_TTL_S`). Si no: `400 invalid_grant`.
4. Opcional: puedes pedir un `scope` **más reducido** que el original; más amplio da
   `invalid_scope`.
5. Marca el refresh token como **usado** y entrega un par nuevo: access token **y refresh token
   nuevo**.

**Consecuencias para tu código** [DOC: D2L lo describe como "single-use"]:

- Después de cada refresco, **guarda el refresh token nuevo**. El viejo ya no sirve.
- Si dos peticiones de EduTrace refrescan al mismo tiempo con el mismo refresh token, una gana y la
  otra recibe `invalid_grant`. Diseña para que solo una petición refresque a la vez (por usuario).
- [APROX] El mock **no** revoca la cadena entera cuando alguien reusa un refresh token viejo (algunos
  servidores lo hacen como defensa). No dependas de ninguno de los dos comportamientos.

---

## 6. Tabla de errores del flujo

| Dónde | Respuesta | Causa típica |
|---|---|---|
| `/oauth2/auth` | Página 400 sin redirección | `client_id` mal copiado, o `redirect_uri` distinta en un carácter |
| Callback | `?error=invalid_scope` | Pediste un scope que la app no tiene registrado |
| Callback | `?error=unsupported_response_type` | `response_type` no es `code` |
| Callback | `?error=access_denied` | El usuario pulsó Cancelar |
| Login | 400 "La sesión del formulario expiró" | Cookie `mock_login_csrf` ausente (otra pestaña, cookies bloqueadas, cambiaste entre `localhost` y `127.0.0.1`) |
| Login | 401 "Usuario o contraseña incorrectos" | Credenciales malas o usuario inactivo |
| Token | `400 invalid_request` | Mandaste JSON en vez de formulario, o Basic + secreto en el cuerpo |
| Token | `401 invalid_client` | Secreto incorrecto o `client_id` de una app de otro tipo |
| Token | `400 invalid_grant` | Código usado, vencido, de otra app, o `redirect_uri` distinta |
| Token | `400 unsupported_grant_type` | `grant_type` mal escrito |
| Token (refresh) | `400 invalid_grant` | Refresh token ya usado (no guardaste el nuevo) o vencido |

Los errores del endpoint de token son JSON: `{"error": "...", "error_description": "..."}`
[APROX: formato del RFC 6749 §5.2].

---

## 7. Qué NO hace el mock en este flujo

- **PKCE** (`code_challenge` / `code_verifier`): no está en la documentación de D2L. Si lo mandas,
  el mock lo ignora (no falla, pero tampoco te protege). No asumas que Brightspace lo valida.
- **OpenID Connect**: no hay `id_token` ni `nonce`.
- **Revocar tokens** o consentimientos por API.
- **Páginas con la marca de D2L**: las páginas del mock son genéricas y dicen "MOCK".

## 8. Checklist para tu cliente

- [ ] `AUTH_BASE_URL` y `API_BASE_URL` configurables, no fijas en el código.
- [ ] `state` aleatorio por intento, guardado en el servidor (o en la sesión), comparado en el callback y descartado después.
- [ ] El callback maneja `error` antes que `code`.
- [ ] `redirect_uri` idéntica en registro, en `/oauth2/auth` y en el canje.
- [ ] El secreto de la app vive en una variable de entorno, nunca en el repositorio ni en el frontend.
- [ ] Tokens guardados en el servidor (base de datos), nunca en el navegador ni en una cookie legible.
- [ ] Se lee `expires_in`; se refresca antes de que venza o al recibir `403 Invalid Token`.
- [ ] Tras cada refresco se guarda el refresh token nuevo; un solo refresco a la vez por usuario.
- [ ] La identidad se toma de `whoami`, no del contenido del token.
