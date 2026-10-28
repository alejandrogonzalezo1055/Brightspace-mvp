# 08 · Operación, pruebas y solución de problemas

---

## 1. Variables de entorno (`app/config.py`)

| Variable | Por defecto | Qué controla | Cuándo cambiarla |
|---|---|---|---|
| `DATA_DIR` | `./data` (en Docker: `/data`) | Dónde viven la base, la clave de firma y los archivos | Rara vez |
| `AUTH_BASE_URL` | `http://localhost:8800` | URL pública del servidor de autorización. Define el `aud` que deben llevar las aserciones JWT | Siempre que accedas por otra dirección (IP del servidor, túnel HTTPS) |
| `API_BASE_URL` | `http://localhost:8800` | URL pública de la API. Se usa para armar los enlaces `Next` de paginación | Igual que la anterior |
| `TENANT_ID` | `6c3d1a0e-...0001` | Claim `tenantid` del token | No hace falta |
| `LP_VERSIONS` / `LE_VERSIONS` | `1.46,1.47,1.48,1.49` / `1.79,1.80,1.81,1.82` | Versiones aceptadas en las rutas | Si quieres simular otra versión |
| `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_WINDOW_S` | `300` / `60` | Tamaño de la cubeta y tiempo de rellenado | Para probar el manejo del 429 (ponla en 5, por ejemplo) |
| `PAGE_SIZE` | `100` | Tamaño de página | Para probar la paginación (ponla en 1) |
| `CORE_SCOPE_GRANTS_ALL` | `false` | Si `core:*:*` abre todas las rutas | Normalmente nunca |
| `ALLOW_INSECURE_JWKS` | `true` | Permite JWKS por `http://` y `file://` | Ponla en `false` para simular la exigencia de HTTPS de Brightspace |
| `MAX_JSON_BYTES` | `1048576` (1 MB) | Tamaño máximo de un JSON | — |
| `MAX_UPLOAD_BYTES` | `52428800` (50 MB) | Tamaño máximo de una entrega | Si tu servidor tiene poco disco |
| `REFRESH_TOKEN_TTL_S` | `2592000` (30 días) | Vida del refresh token | Para probar refresh tokens vencidos |
| `COOKIE_SECURE` | `false` | Cookie de sesión del login solo por HTTPS | `true` **solo** cuando el mock esté detrás de HTTPS |
| `MOCK_DEMO_PASSWORD` | `Mock2026!` | Contraseña de los usuarios de demo | Solo tiene efecto al **crear** los datos |

Fijos en el código: vida del código de autorización (300 s) y de la sesión de login (8 h).

> `COOKIE_SECURE=true` sin HTTPS rompe el login cuando entras por IP o por un nombre de dominio:
> el navegador no guarda ni devuelve cookies marcadas como seguras en una conexión HTTP, y el mock
> responde "La sesión del formulario expiró" en cada intento. (Con `localhost` algunos navegadores
> sí las aceptan, así que el problema puede no aparecer en tu portátil.)

---

## 2. Correrlo

### En tu portátil (sin Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                                  # opcional: 34 pruebas
uvicorn app.main:create_app --factory --port 8800
```

- `--factory` es obligatorio (ver `01-ARQUITECTURA.md`, sección 4).
- La terminal debe quedar abierta. Para correrlo en segundo plano en Linux, usa Docker o systemd.
- Para que otras máquinas lo alcancen: `--host 0.0.0.0`.

### Con Docker (tu servidor)

`docker-compose.yml`:

- Construye la imagen con `python:3.11-slim`.
- Publica el puerto `8800`.
- Monta `./data` (en el servidor) como `/data` (en el contenedor): los datos sobreviven a reinicios.
- `restart: unless-stopped`: arranca solo cuando arranca Docker.
- `mem_limit: 256m`: Docker lo mata si pasa de 256 MB (usa ~60).
- El contenedor **ya ejecuta uvicorn** al arrancar (`CMD` del `Dockerfile`, con `--proxy-headers`).

| Para… | Comando |
|---|---|
| Construir y arrancar | `sudo docker compose up -d --build` |
| Ver si está corriendo | `sudo docker compose ps` |
| Ver los logs en vivo | `sudo docker compose logs -f brightspace-mock` |
| Aplicar cambios del `docker-compose.yml` | `sudo docker compose up -d` |
| Aplicar cambios del código | `sudo docker compose up -d --build` |
| Detener | `sudo docker compose down` |
| Comandos de administración | `sudo docker compose exec brightspace-mock python admin.py <comando>` |

**No** lances `uvicorn` con `docker compose exec`: el contenedor ya tiene uno escuchando en el 8800,
y el segundo falla con `address already in use`.

Los archivos de `./data` los crea el contenedor como `root`: para borrarlos desde el servidor
necesitas `sudo`.

---

## 3. `admin.py`

| Comando | Qué hace |
|---|---|
| `register-app --name N --redirect-uri U --scopes "S" [--lifetime 3600] [--no-refresh] [--no-consent]` | Registra una app Authorization Code. Imprime `client_id` y `client_secret` (el secreto solo esa vez) |
| `register-s2s --name N --jwks-url U --scopes "S" [--service-user svc_edutrace] [--lifetime 3600]` | Registra una app Client Credentials. Imprime `client_id` y el `aud` exacto |
| `list-apps` | Lista las apps (sin secretos) |
| `delete-app <client_id>` | Borra la app, sus códigos, refresh tokens y consentimientos (los access tokens ya emitidos siguen valiendo hasta vencer) |
| `users` | Lista usuarios, rol de organización y cursos con su rol, y la contraseña de demo |
| `reset` | **Borra toda la carpeta de datos** (base, apps, entregas, clave de firma) y recarga la demo |

Todos los comandos, antes de actuar, crean las tablas y cargan la demo si la base está vacía.

### Cómo reiniciar los datos de forma segura

`reset` borra la carpeta mientras el servidor puede estar usándola, y el servidor guarda la clave
de firma en memoria. Además, en Docker `/data` es un punto de montaje, y Python no puede borrar un
punto de montaje, así que `reset` **probablemente falle a mitad de camino dentro del contenedor**
(no lo pude probar). El procedimiento seguro:

- **Docker**: `sudo docker compose down` → `sudo rm -rf data/*` → `sudo docker compose up -d`.
- **Sin Docker**: detener uvicorn (Ctrl+C) → `python admin.py reset` → arrancar uvicorn.

Después de reiniciar: hay que **volver a registrar las apps** (cambian los `client_id` y secretos) y
todos los tokens anteriores dejan de servir (clave nueva).

---

## 4. Las pruebas (`tests/`)

```bash
python -m pytest            # todas
python -m pytest -v         # con el nombre de cada una
python -m pytest -k refresh # solo las que contienen "refresh" en el nombre
```

Cada prueba crea una app nueva con su propia carpeta temporal: no tocan `data/` ni interfieren
entre sí.

### `conftest.py` (herramientas compartidas)

| Fixture / función | Qué hace |
|---|---|
| `settings` | Configuración con carpeta temporal y límite de tasa muy alto |
| `app`, `client` | La app y un cliente HTTP de pruebas que **no sigue redirecciones** (para inspeccionar cada 302) |
| `token_for(user_id, scope=..., lifetime=...)` | Emite un access token directamente con la clave del mock, **sin pasar por OAuth**. Lo usan las pruebas de la API para no repetir el login en cada prueba. El flujo OAuth real se prueba aparte |
| `browser_login_and_authorize` | Simula al navegador: abre `/oauth2/auth`, lee los campos ocultos del HTML, envía login y consentimiento |

### `test_oauth.py` (14 pruebas)

| Prueba | Verifica |
|---|---|
| `test_authorization_code_flow_end_to_end` | El flujo completo; campos de la respuesta del token; `Cache-Control: no-store`; `whoami` con el token |
| `test_client_secret_in_body_also_works` | Autenticar la app con el secreto en el cuerpo |
| `test_consent_is_remembered` | La segunda vez no se pide login ni consentimiento |
| `test_redirect_uri_must_match_exactly` | Una barra de más → página 400 sin redirigir |
| `test_unknown_client_shows_error_page` | `client_id` desconocido → página 400 sin redirigir |
| `test_unregistered_scope_redirects_with_error` | Scope no registrado → redirige con `invalid_scope` y el `state` |
| `test_user_denies_consent` | Cancelar → `access_denied` |
| `test_wrong_password_and_csrf` | Contraseña mala → 401; CSRF falso → 400 |
| `test_code_is_single_use_and_bound_to_redirect_uri` | `redirect_uri` distinta → `invalid_grant`; segundo uso → `invalid_grant` |
| `test_wrong_secret_is_invalid_client` | Secreto malo → 401 `invalid_client` |
| `test_refresh_tokens_are_single_use` | Refresh entrega uno nuevo; reusar el viejo → `invalid_grant`; el nuevo sí sirve |
| `test_token_endpoint_requires_form_encoding` | JSON en el endpoint de token → `invalid_request` |
| `test_client_credentials_flow` | Aserción válida → token; el usuario de servicio ve carpetas ocultas |
| `test_client_credentials_rejections` | `jti` repetido, `aud` ajeno, vida > 5 min, `kid` inexistente, firma con otra clave, scope no registrado |

### `test_api.py` (20 pruebas)

| Prueba | Verifica |
|---|---|
| `test_missing_bad_or_expired_token_is_403_invalid_token` | Sin token, basura o vencido → 403 `Invalid Token` |
| `test_authentication_header_variant_is_accepted` | Encabezado `Authentication` |
| `test_missing_scope_is_403` | Scope insuficiente → 403 |
| `test_wildcard_and_comma_scopes` | `dropbox:*:read`, `read,write` pasan; `core:*:*` no (modo estricto) |
| `test_unsupported_version_and_trailing_slash_are_404` | Versión, barra final e ID no numérico → 404 |
| `test_versions_routes_are_anonymous` | Rutas de versiones sin token; chequeo masivo |
| `test_rate_limit_headers_and_429` | Encabezados del límite y 429 con `Retry-After` |
| `test_myenrollments_is_a_paged_result_set` | Forma de `PagedResultSet` y de `MyOrgUnitInfo` |
| `test_myenrollments_paging_with_bookmark` | Paginación con `bookmark` (página de tamaño 1) |
| `test_users_visibility` | Quién puede ver a quién en `users/(userId)` |
| `test_classlist_hides_private_fields_from_students` | Campos privados en `null` para estudiantes; `classlist/paged` |
| `test_other_course_is_forbidden` | Docente/estudiante de otro curso → 403; curso inexistente → 404 |
| `test_students_do_not_see_hidden_folders_or_counts` | Carpeta oculta → 404 al estudiante; conteos −1; conteos reales al docente |
| `test_student_submits_with_multipart_mixed` | Entrega con dos archivos; `mysubmissions`; descarga; otro estudiante no puede descargar |
| `test_submission_errors` | Docente no entrega (403); carpeta cerrada (403); JSON en vez de multipart (415); sin archivo (400); JSON roto (400) |
| `test_instructor_lists_submissions_paged` | Lista paginada con un estado por estudiante; estudiante no puede listar |
| `test_create_and_update_folder` | Crear con `RichTextInput` HTML; `PUT` parcial; fecha mal formada; estudiante no crea; 415 |
| `test_feedback_draft_then_publish_updates_gradebook` | Borrador invisible al estudiante; publicar → `Status` 3, nota 4/5 en el libro, nota final |
| `test_feedback_validation` | Estudiante no publica; `Score` no numérico; entidad de otro curso; grupo |
| `test_grade_values` | `PUT` de nota; exceder el máximo; tipo incorrecto; comentarios privados; filtros de `values/` |

---

## 5. Probar a mano con Postman

### Sin token

`GET http://<host>:8800/d2l/api/versions/` (con la barra final).

### Con token: método manual (para entender el flujo)

1. Registrar la app: `admin.py register-app --name Postman --redirect-uri http://localhost:9000/callback --scopes "users:own_profile:read enrollment:own_enrollment:read dropbox:folders:read"`.
2. En el navegador abrir:
   `http://<host>:8800/oauth2/auth?response_type=code&client_id=<ID>&redirect_uri=http://localhost:9000/callback&scope=users:own_profile:read%20enrollment:own_enrollment:read%20dropbox:folders:read&state=prueba123`
3. Iniciar sesión (`estudiante1` / `Mock2026!`) y autorizar.
4. El navegador intenta abrir `localhost:9000/callback?code=...&state=prueba123`. **La página no
   carga y es normal** (no hay nada en el puerto 9000). Copiar `code` de la barra de direcciones.
   Vence en 5 minutos y sirve una vez.
5. En Postman: `POST http://<host>:8800/core/connect/token`
   - *Authorization*: Basic Auth con `client_id` / `client_secret`.
   - *Body*: `x-www-form-urlencoded` con `grant_type=authorization_code`, `code=<code>`,
     `redirect_uri=http://localhost:9000/callback`.
6. Con el `access_token`: *Authorization* → *Bearer Token*, y probar
   `/d2l/api/lp/1.49/users/whoami`, `/d2l/api/lp/1.49/enrollments/myenrollments/`,
   `/d2l/api/le/1.82/6650/dropbox/folders/`.
7. Probar el refresh: mismo `POST` del paso 5 con `grant_type=refresh_token` y
   `refresh_token=<el tuyo>`. Repetir con el **mismo** refresh token para ver el `invalid_grant`.

`<host>` es `localhost` si el mock corre en la misma máquina que Postman, o la IP del servidor.
La `redirect_uri` usa `localhost` siempre: es una dirección a la que va **tu navegador**, no el mock.

### Con el asistente OAuth 2.0 de Postman

Grant type *Authorization Code* (sin PKCE); Auth URL `.../oauth2/auth`; Access Token URL
`.../core/connect/token`; *Client Authentication: Send as Basic Auth header*; registrar la app con
la **Callback URL exacta** que muestre Postman.

### Para ver errores a propósito

| Quieres ver | Haz |
|---|---|
| `403 Invalid Token` | Cambia una letra del token |
| `403 Insufficient scope` | Pide `/d2l/api/le/1.82/6650/grades/` (tu token no tiene `grades:*`) |
| 404 por versión | Cambia `1.49` por `1.20` |
| 404 por barra final | Quita la `/` final de `.../folders/` |
| 403 por curso ajeno | Con `estudiante1`, pide `/d2l/api/le/1.82/6651/dropbox/folders/` |
| 429 | Arranca con `RATE_LIMIT_CAPACITY=5` y haz 6 peticiones seguidas |

---

## 6. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `connect ECONNREFUSED 127.0.0.1:8800` | Nada escucha en ese puerto: el mock no está corriendo, o corre en otro puerto u otra máquina | Arrancar uvicorn y dejar la terminal abierta; con Docker, `docker compose ps`; usar la IP correcta |
| `address already in use` al arrancar | Ya hay algo en el puerto (en Docker: el uvicorn del propio contenedor) | `sudo ss -tlnp \| grep 8800`; en Docker no arranques uvicorn a mano |
| `Attribute "app" not found` o error parecido al arrancar | Faltó `--factory` | `uvicorn app.main:create_app --factory ...` |
| `ModuleNotFoundError` | Entorno virtual sin activar o dependencias sin instalar | Activar `.venv` y `pip install -r requirements.txt` |
| 404 con cuerpo vacío | Barra final, versión, ID no numérico o ruta mal escrita | Comparar con `05-REFERENCIA-API.md` |
| `403 Invalid Token` | Token vencido, mal copiado, sin `Bearer`, o firmado con una clave anterior (se reinició la carpeta de datos) | Pedir un token nuevo |
| Página "No se puede continuar" en `/oauth2/auth` | `client_id` o `redirect_uri` no coinciden con lo registrado | `admin.py list-apps` y comparar carácter por carácter |
| `invalid_grant` al canjear el código | Código usado (recargaste la página), vencido o `redirect_uri` distinta | Repetir desde `/oauth2/auth` |
| `invalid_client` en Client Credentials con "aserción inválida" | Casi siempre `aud` incorrecto | El `aud` debe ser `AUTH_BASE_URL` + `/core/connect/token`; revisar que `AUTH_BASE_URL` sea la dirección real |
| "La sesión del formulario expiró" en el login | La cookie no llegó: alternaste entre `localhost` y `127.0.0.1`, cookies bloqueadas, o `COOKIE_SECURE=true` sin HTTPS | Usar siempre el mismo host; revisar `COOKIE_SECURE` |
| Los enlaces `Next` apuntan a `localhost` | `API_BASE_URL` sin actualizar | Ponerle la dirección real y reiniciar |
| Entregar da 403 "at this time" en las carpetas 701/702 | Pasaron más de 21 días desde que se cargaron los datos y la carpeta se cerró | Reiniciar los datos (sección 3) o crear otra carpeta |
| Error 500 | Un fallo del mock | `docker compose logs` o la terminal de uvicorn muestran el error completo |
