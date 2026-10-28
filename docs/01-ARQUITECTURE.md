# 01 · Arquitectura

## 1. Qué es el mock y qué no es

El mock es **un solo proceso Python** (FastAPI servido por uvicorn) que hace dos papeles que en la
vida real son dos sistemas distintos:

| Papel | En Brightspace real | En el mock |
|---|---|---|
| **Servidor de autorización** (login, consentimiento, emisión de tokens) | `https://auth.brightspace.com` | rutas `/oauth2/auth`, `/core/connect/token` |
| **Servidor de recursos** (la API con los datos) | `https://<universidad>.brightspace.com` | rutas `/d2l/api/...` |

Como en real son dos hosts, el mock tiene **dos variables de configuración separadas**
(`AUTH_BASE_URL` y `API_BASE_URL`) aunque ambas apunten al mismo proceso. El cliente de EduTrace
también debe tenerlas separadas: el día que se conecte a Brightspace real, solo cambian esas dos URL.

No es: una copia del interior de Brightspace, un LMS con interfaz web, ni un servidor apto para
datos reales (las contraseñas de demo son públicas y corre sin HTTPS por defecto).

## 2. Por qué FastAPI + SQLite

- **FastAPI**: es lo que vas a usar en tu parte de EduTrace, así que leer el mock también te sirve
  para aprender el framework. Valida parámetros de ruta y query, y genera documentación en
  `/.mock/docs`.
- **SQLite** (módulo `sqlite3` de la librería estándar): un archivo, sin servidor de base de datos
  que instalar ni mantener. Para un mock con decenas de usuarios es más que suficiente.
- **PyJWT + cryptography**: firmar y verificar JWT con RSA, que es lo que exige el flujo OAuth.
- **httpx**: para descargar el JWKS de una app en el flujo servidor a servidor.
- **python-multipart**: para leer los formularios HTML de login y consentimiento.

Consumo medido: unos **60 MB de RAM** en reposo.

## 3. Mapa de archivos

```
mock-brightspace/
├── app/
│   ├── main.py            ← arranque: crea la app, middleware, manejo de errores, registra rutas
│   ├── config.py          ← lee las variables de entorno (Settings)
│   ├── db.py              ← esquema SQLite, conexión por petición, formato de fechas D2L
│   ├── errors.py          ← errores en formato D2L (texto) y OAuth (JSON)
│   ├── seed.py            ← datos de demostración (se cargan si la base está vacía)
│   ├── apps.py            ← registrar / listar / borrar aplicaciones OAuth
│   ├── oauth/
│   │   ├── routes.py      ← HTTP del servidor de autorización (login, consentimiento, token)
│   │   ├── service.py     ← la lógica: validar solicitudes, emitir códigos y tokens
│   │   └── pages.py       ← HTML de login, consentimiento y error
│   ├── security/
│   │   ├── passwords.py   ← PBKDF2 para contraseñas y secretos; SHA-256 para tokens guardados
│   │   ├── keys.py        ← clave RSA con la que el mock firma los access tokens
│   │   ├── tokens.py      ← emitir y verificar access tokens (JWT RS256)
│   │   ├── scopes.py      ← gramática de scopes, subconjuntos y "¿alcanza este scope?"
│   │   ├── ratelimit.py   ← token bucket del límite de tasa
│   │   └── assertions.py  ← verificar la aserción JWT del flujo servidor a servidor
│   └── api/
│       ├── deps.py        ← dependencias comunes: conexión, quién llama, scope, versión, rol en el curso
│       ├── formats.py     ← convierte filas SQLite en las estructuras JSON de D2L
│       ├── common.py      ← leer JSON con las reglas de D2L; escribir notas
│       ├── versions.py    ← /d2l/api/versions/...
│       ├── users.py       ← whoami y users/(userId)
│       ├── enrollments.py ← myenrollments, usuarios de un curso, classlist
│       ├── dropbox.py     ← carpetas, entregas, retroalimentación
│       └── grades.py      ← ítems de calificación y notas
├── admin.py               ← línea de comandos (equivale a Admin Tools de Brightspace)
├── tests/                 ← 34 pruebas de punta a punta
├── Dockerfile, docker-compose.yml, requirements*.txt
└── data/                  ← se crea al arrancar (ver sección 6)
```

La división `oauth/routes.py` (HTTP) vs `oauth/service.py` (lógica) sigue la misma idea de capas
que pediste para el backend: la ruta recibe la petición y arma la respuesta; la lógica decide.
En `api/` la separación es por recurso (un archivo por grupo de rutas de D2L) y lo común está en
`deps.py`, `formats.py` y `common.py`.

## 4. Arranque: `create_app` (app/main.py)

El mock usa una **fábrica**: la app no existe al importar el módulo, se crea al llamar a
`create_app()`. Por eso el comando lleva `--factory`:

```
uvicorn app.main:create_app --factory --port 8800
```

Sin `--factory`, uvicorn buscaría una variable `app` que no existe y fallaría. La razón de usar
fábrica: las pruebas crean una app nueva por prueba, cada una con su propia carpeta de datos
temporal, sin tocar `data/`.

`create_app(settings)` hace, en orden:

1. Lee la configuración (`Settings`, ver `08-OPERACION-Y-PRUEBAS.md`).
2. Crea `data/` y `data/uploads/` si no existen.
3. Crea las tablas si no existen (`init_db`) y activa el modo WAL de SQLite.
4. Si la tabla de usuarios está vacía, carga los datos de demostración (`seed_demo_if_empty`).
5. Crea la app FastAPI con `redirect_slashes=False` (ver sección 7) y la documentación en
   `/.mock/docs`.
6. Carga (o genera la primera vez) la clave RSA de firma: `data/signing_key.pem`.
7. Crea el limitador de tasa en memoria.
8. Registra el middleware, los manejadores de errores y todos los routers.

## 5. El viaje de una petición a la API

Ejemplo: `GET /d2l/api/le/1.82/6650/dropbox/folders/` con `Authorization: Bearer eyJ...`

![Diagrama de Secuencia](Images/1%20Architecture.png)

Puntos importantes de este recorrido:

- **El token se lee en el middleware, pero se exige en la dependencia.** El middleware solo
  intenta verificarlo y guarda el resultado (o `None`). Así las rutas anónimas (versiones) pasan, y
  las protegidas fallan en `current_caller` con `403 Invalid Token` si no hay claims válidos.
- **El límite de tasa se aplica antes de saber si el token es bueno.** Una petición con token
  inválido igual gasta un crédito (de la cubeta de la IP, porque no se pudo saber de qué app es).
- **El orden de los chequeos importa** y determina qué error ves:
  1. ruta inexistente o parámetro de ruta no entero → **404**;
  2. versión no soportada → **404**;
  3. token ausente/inválido/vencido → **403 `Invalid Token`**;
  4. scope insuficiente → **403 `Insufficient scope...`**;
  5. curso inexistente → **404**;
  6. sin rol suficiente en el curso → **403**;
  7. validaciones del cuerpo → **400 / 413 / 415**.

  Ejemplo práctico: un estudiante sin scope que pide un curso inexistente ve el 403 de scope, no
  el 404 del curso, porque el scope se revisa antes.
- **Una transacción por petición**: si la ruta lanza un error a mitad de camino, nada de lo que
  alcanzó a escribir queda guardado (rollback).

## 6. La carpeta `data/`

| Ruta | Qué es | Si la borras… |
|---|---|---|
| `data/brightspace_mock.sqlite3` (+ `-wal`, `-shm`) | La base de datos | Se pierden usuarios, apps registradas, entregas y notas; al arrancar se recarga la demo |
| `data/signing_key.pem` | Clave privada RSA con la que se firman los access tokens | Se genera una nueva: **todos los tokens emitidos dejan de servir** |
| `data/uploads/<idEntrega>/<idArchivo>` | Los archivos entregados por los estudiantes | Las descargas de esos archivos fallan |

En Docker, `data/` dentro del contenedor es `/data`, montado desde `./data` de la carpeta del
proyecto (por eso sobrevive a reinicios del contenedor).

## 7. Decisiones de diseño y su porqué

| Decisión | Por qué |
|---|---|
| `redirect_slashes=False`: `/folders` y `/folders/` son rutas distintas | La documentación de D2L escribe las rutas con o sin barra final de forma precisa. Si el mock redirigiera, tu cliente podría quedar con la ruta mal escrita y funcionar aquí pero no allá |
| Errores de la API en **texto plano**, no JSON | D2L no define un esquema JSON de error; documenta textos como `Invalid Token` |
| Token inválido → **403**, no 401 | Así lo documenta D2L. Es distinto al estándar común; tu cliente debe manejarlo |
| Parámetro de ruta que no es entero → **404** | D2L documenta que si un parámetro no se puede interpretar, la ruta "no existe" |
| Conexión SQLite nueva en cada petición | SQLite es un archivo local: abrirlo es barato y así no se comparten conexiones entre hilos. Se usa `check_same_thread=False` porque FastAPI puede abrir la conexión en un hilo y usarla en otro **dentro de la misma petición** |
| En la base solo se guarda el **hash** de códigos, tokens de refresco y sesiones | Si alguien copia el archivo SQLite, no obtiene credenciales usables |
| Los IDs son números inventados (6650, 3101…) | Brightspace usa enteros (`D2LID`). El cliente nunca debe tenerlos fijos: los descubre con la API |
| Límite de tasa y sesiones de login en memoria | Simplicidad. Consecuencia: se reinician al reiniciar el proceso |
| Rutas solo de lo que EduTrace necesita | Un MVP: cuanto menos código, menos lugares donde el mock puede diferir de Brightspace |
