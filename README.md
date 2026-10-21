# Mock de Brightspace para EduTrace

Un Brightspace de mentiras, **mínimo pero fiel a la interfaz documentada por D2L**, para probar que
EduTrace sabe hablar con el Brightspace real: OAuth 2.0 (las dos concesiones), tokens Bearer,
scopes, límite de tasa y las rutas de la API Valence que EduTrace necesita (usuarios, cursos,
lista de clase, carpetas de entrega, entregas, retroalimentación y notas).

- Qué se copió de la documentación oficial y qué se aproximó: **[docs/ESPECIFICACION.md](docs/ESPECIFICACION.md)**.
  Léelo antes de programar el cliente: ahí están las rutas, los scopes y los formatos.
- Python 3.10 o superior (probado con 3.11). Usa unos 60 MB de RAM.

---

## 1. Correrlo en tu computador

```bash
python3 -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest                   # 34 pruebas; deben pasar todas
uvicorn app.main:create_app --factory --port 8800
```

La primera vez crea `data/` con la base SQLite, la clave de firma y los datos de demostración.

- Versiones de la API: http://localhost:8800/d2l/api/versions/
- Documentación interactiva (solo existe en el mock): http://localhost:8800/.mock/docs

### Usuarios de demostración (contraseña `Mock2026!`)

| Usuario | Rol | Curso |
|---|---|---|
| `docente1` | Instructor | 6650 Introducción a la Programación |
| `estudiante1`, `estudiante2`, `estudiante3` | Student | 6650 |
| `docente2` / `estudiante4` | Instructor / Student | 6651 Estructuras de Datos |
| `admin` | Administrador de la organización | todos |
| `svc_edutrace` | Usuario de servicio (sin login; para servidor a servidor) | todos |

En el curso 6650 hay carpetas de entrega 701 y 702 (abiertas, enlazadas a los ítems de nota 5001
y 5002), 703 (oculta) y 704 (cerrada). `estudiante1` ya tiene una entrega en la 701.
`python admin.py users` lo lista todo; `python admin.py reset` vuelve al estado inicial.

> Los IDs son inventados. **EduTrace no debe tener ningún ID fijo en su código**: los descubre con
> `whoami`, `myenrollments`, etc., igual que tendrá que hacerlo con Brightspace real.

---

## 2. Registrar EduTrace como aplicación

En Brightspace esto lo hace un administrador desde *Manage Extensibility > OAuth 2.0*. En el mock:

**Usuarios interactivos (Authorization Code)**, para que docentes y estudiantes entren desde EduTrace:

```bash
python admin.py register-app --name EduTrace \
  --redirect-uri http://localhost:8000/auth/brightspace/callback \
  --scopes "users:own_profile:read enrollment:own_enrollment:read enrollment:orgunit:read dropbox:folders:read,write grades:gradeobjects:read grades:gradevalues:read grades:own_grades:read"
```

Imprime `client_id` y `client_secret`. El secreto **solo se muestra esa vez**. La `redirect_uri` debe
ser exactamente la que use EduTrace: una barra de más y el mock la rechaza.

**Servidor a servidor (Client Credentials con JWT)**, para tareas de fondo sin usuario:

```bash
python admin.py register-s2s --name "EduTrace sync" \
  --jwks-url http://localhost:8000/.well-known/jwks.json \
  --scopes "enrollment:orgunit:read dropbox:folders:read" --service-user svc_edutrace
```

EduTrace debe publicar su clave pública en esa URL (JWKS) y firmar cada aserción con la privada.
El comando imprime el `aud` exacto que debe llevar la aserción.

---

## 3. Qué tiene que hacer el cliente de EduTrace (sin código)

1. **Dos URL configurables**: la de autorización y la de la API. En real son
   `https://auth.brightspace.com` y `https://<universidad>.brightspace.com`; en el mock, la misma.
2. **Login**: redirigir el navegador a `/oauth2/auth` con `response_type=code`, `client_id`,
   `redirect_uri`, `scope` y un `state` aleatorio. Al volver, **comprobar que el `state` coincide**
   (eso evita CSRF) antes de usar el `code`.
3. **Canjear el código** en `POST /core/connect/token`, en `application/x-www-form-urlencoded`, con
   `client_id`/`client_secret` por HTTP Basic. El código sirve **una sola vez** y vence en minutos.
4. **Guardar los tokens en el servidor**, nunca en el navegador. Leer `expires_in`: no asumir la duración.
5. **Refrescar** con `grant_type=refresh_token`. Cada refresh token sirve **una sola vez**: guarda
   siempre el nuevo. Si dos peticiones refrescan a la vez con el mismo token, una falla; diseña para eso.
6. **Llamar a la API** con `Authorization: Bearer <token>`. Un **403 con `Invalid Token`** significa
   token vencido o inválido (Brightspace no usa 401 aquí); un 403 con otro texto es falta de scope o
   de permiso.
7. **Respetar el límite de tasa**: leer `X-Rate-Limit-Remaining` y, ante un 429, esperar `Retry-After`.
8. **Paginar**: `PagingInfo.Bookmark` / `HasMoreItems` en unos listados y `Next` en otros.

Las pruebas en `tests/` hacen cada uno de estos pasos contra el mock. Sirven como referencia de las
peticiones exactas.

---

## 4. Ponerlo en tu servidor (Ubuntu Server, i3, 4 GB)

El mock cabe de sobra junto a CasaOS y Crafty: no hace falta apagarlos. Lo que sí conviene es
**no tener un servidor de Minecraft prendido durante la presentación**.

### Opción A: con Docker (CasaOS ya trae Docker)

```bash
git clone <tu-repo> mock-brightspace && cd mock-brightspace
docker compose up -d --build
docker compose exec brightspace-mock python admin.py register-app ...   # registrar EduTrace
```

> No pude probar la imagen de Docker aquí (no había servicio de Docker disponible). El código sí está
> probado; si el `build` falla, avísame con el error.

### Opción B: sin Docker, con systemd

```bash
sudo apt install python3-venv
cd /opt && sudo git clone <tu-repo> mock-brightspace && cd mock-brightspace
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
```

Crea `/etc/systemd/system/brightspace-mock.service`:

```ini
[Unit]
Description=Mock de Brightspace para EduTrace
After=network.target

[Service]
WorkingDirectory=/opt/mock-brightspace
Environment=DATA_DIR=/opt/mock-brightspace/data
Environment=AUTH_BASE_URL=http://IP-DEL-SERVIDOR:8800
Environment=API_BASE_URL=http://IP-DEL-SERVIDOR:8800
ExecStart=/opt/mock-brightspace/.venv/bin/uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8800 --proxy-headers
Restart=on-failure
MemoryMax=256M

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now brightspace-mock
journalctl -u brightspace-mock -f      # ver los logs
```

### HTTPS y acceso desde fuera de tu casa

Brightspace real solo funciona por HTTPS, y tu parte es la seguridad, así que pruébalo también así.
Dos caminos que no requieren abrir puertos en el router:

- **Cloudflare Tunnel** (requiere un dominio en Cloudflare) o **Tailscale Funnel**: te dan una URL
  HTTPS pública que llega al puerto 8800.
- Luego pon esa URL en `AUTH_BASE_URL` y `API_BASE_URL`, y `COOKIE_SECURE=true`.

Si `AUTH_BASE_URL` no coincide con la URL real por la que llegan las peticiones, las aserciones JWT
del flujo servidor a servidor fallan por `aud` incorrecto. Es a propósito: así se comporta Brightspace.

---

## 5. Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `DATA_DIR` | `./data` | Base SQLite, archivos entregados y clave de firma |
| `AUTH_BASE_URL` / `API_BASE_URL` | `http://localhost:8800` | URL pública del mock |
| `MOCK_DEMO_PASSWORD` | `Mock2026!` | Contraseña de los usuarios de demo (solo al crear la base) |
| `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_WINDOW_S` | 300 / 60 | Cubeta del límite de tasa por app |
| `PAGE_SIZE` | 100 | Tamaño de página de los listados |
| `CORE_SCOPE_GRANTS_ALL` | `false` | Si `core:*:*` abre todas las rutas (estricto por defecto) |
| `ALLOW_INSECURE_JWKS` | `true` | Permite JWKS por `http://` y `file://` (en real solo HTTPS) |
| `MAX_UPLOAD_BYTES` | 50 MB | Tamaño máximo de una entrega |
| `REFRESH_TOKEN_TTL_S` | 30 días | Vida del refresh token |
| `COOKIE_SECURE` | `false` | Cookie de sesión solo por HTTPS |
| `LP_VERSIONS` / `LE_VERSIONS` | `1.46…1.49` / `1.79…1.82` | Versiones anunciadas |

---

## 6. Estructura

```
app/
  main.py          fábrica de la app, middleware de token y límite de tasa, manejo de errores
  config.py        variables de entorno
  db.py            esquema SQLite y formato de fechas de D2L
  seed.py          datos de demostración
  apps.py          registro de aplicaciones OAuth
  oauth/           servidor de autorización: rutas, lógica y páginas de login/consentimiento
  security/        contraseñas, clave de firma, tokens, scopes, límite de tasa, aserciones JWT
  api/             rutas Valence: versiones, usuarios, inscripciones, dropbox, notas
admin.py           línea de comandos de administración
tests/             34 pruebas de punta a punta
docs/ESPECIFICACION.md
```
