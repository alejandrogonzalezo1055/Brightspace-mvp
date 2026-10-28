# Mock de Brightspace para EduTrace

Un Brightspace de mentiras, **mínimo pero fiel a la interfaz documentada por D2L**, para probar que
EduTrace sabe hablar con el Brightspace real: OAuth 2.0 (las dos concesiones), tokens Bearer,
scopes, límite de tasa y las rutas de la API Valence que EduTrace necesita (usuarios, cursos,
lista de clase, carpetas de entrega, entregas, retroalimentación y notas).

- Python 3.10 o superior (probado con 3.11). Usa unos 60 MB de RAM.
- Este README explica **cómo correrlo, cómo conectarlo y cómo entenderlo**. El detalle interno está
  en la carpeta [`docs/`](docs/00-INDICE.md): cada sección de este README termina con una línea
  **Fuente** que dice de qué documento sale lo explicado, para que puedas profundizar.

> **Fuente de esta introducción:** [`docs/00-INDICE.md`](docs/00-INDICE.md) ("La idea en un
> párrafo") y [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §1.

## Índice: ¿qué quieres hacer?

| Quiero… | Ve a                                                           |
|---|----------------------------------------------------------------|
| Entender qué es todo esto sin saber nada de Brightspace | [§0](#0-conceptos-mínimos-si-no-conoces-brightspace)           |
| Ver cómo está organizado el código | [§1](#1-estructura-del-proyecto)                               |
| Correrlo en mi portátil | [§2](#2-correrlo-en-tu-computador)                             |
| Correrlo en mi servidor (Docker o systemd) y ponerle HTTPS | [§3](#3-correrlo-en-tu-servidor)                               |
| Saber qué usuarios, cursos y tareas trae de fábrica | [§4](#4-datos-de-demostración)                                 |
| Registrar EduTrace como aplicación | [§5](#5-registrar-edutrace-como-aplicación)                    |
| Saber qué debe hacer el código de EduTrace | [§6](#6-qué-tiene-que-hacer-el-cliente-de-edutrace-sin-código) |
| Cambiar la configuración | [§7](#7-variables-de-entorno)                                  |
| Arreglar un error | [§8](#8-si-algo-falla)                                         |
| Saber en qué detalles puedo confiar | [§9](#9-qué-tan-fiel-es-al-brightspace-real)                   |

---

## 0. Conceptos mínimos (si no conoces Brightspace)

### 0.1 Qué es Brightspace

**Brightspace** es la plataforma de cursos en línea de la universidad: ahí viven los cursos, las
listas de estudiantes, las tareas y las notas. La empresa que lo hace se llama **D2L** (Desire2Learn).
Brightspace ofrece una API pública llamada **Valence**: es el conjunto de direcciones web (rutas)
con las que otro programa, como EduTrace, puede leer y escribir esos datos sin abrir la página.

Cuatro palabras que verás todo el tiempo:

| Palabra de Brightspace | Qué es | En palabras simples |
|---|---|---|
| **Org unit** (unidad organizacional) | Cualquier nodo de la estructura: la universidad, una facultad, un curso | Un "lugar" con un número (`OrgUnitId`). Aquí nos interesan los **cursos** |
| **Dropbox** (carpeta de entrega) | Una tarea donde los estudiantes suben archivos | El "taller" |
| **Grade object** (ítem de calificación) | Una columna del libro de calificaciones | El "casillero" de la nota de un taller |
| **LP / LE** | Los dos productos de la API: *Learning Platform* (usuarios, inscripciones) y *Learning Environment* (carpetas, notas, lista de clase) | Cada ruta empieza con `/d2l/api/lp/...` o `/d2l/api/le/...`, seguido de un número de versión |

> **Fuente:** [`docs/10-GLOSARIO.md`](docs/10-GLOSARIO.md) (D2L, Valence, Org unit, Dropbox, Grade
> object, LE/LP) y [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md) §4 (versiones
> en la ruta).

### 0.2 Qué es un "mock" y por qué existe

Un **mock** es una imitación de un sistema real para poder probar contra ella. Este mock **imita la
interfaz pública de Brightspace**: las mismas URL, los mismos parámetros, los mismos formatos JSON,
los mismos códigos de error y el mismo flujo OAuth 2.0 que documenta D2L. **No** imita su interior
(su base de datos, sus permisos configurables, su página web).

La regla de diseño: **si el cliente de EduTrace funciona contra el mock, debería funcionar contra
Brightspace real.** Por eso, cuando la documentación de D2L es ambigua, el mock elige el
comportamiento **más estricto**: un cliente que pasa aquí no se rompe después por haberse apoyado en
algo permisivo.

Lo que **no** es: una copia del interior de Brightspace, un LMS con interfaz web, ni un servidor apto
para datos reales (las contraseñas de demostración son públicas y, por defecto, corre sin HTTPS).

> **Fuente:** [`docs/00-INDICE.md`](docs/00-INDICE.md) ("La idea en un párrafo") y
> [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §1 ("Qué es el mock y qué no es").

### 0.3 Dos servidores en uno

En la vida real, Brightspace son **dos sistemas distintos**. El mock hace los dos papeles dentro de
**un solo proceso**:

| Papel | Qué hace | En Brightspace real | En el mock |
|---|---|---|---|
| **Servidor de autorización** | Login, consentimiento y emisión de tokens | `https://auth.brightspace.com` | Rutas `/oauth2/auth` y `/core/connect/token` |
| **Servidor de recursos** (la API) | Entrega los datos | `https://<universidad>.brightspace.com` | Rutas `/d2l/api/...` |

Por eso hay **dos variables de configuración** (`AUTH_BASE_URL` y `API_BASE_URL`), aunque apunten al
mismo mock. EduTrace también debe tenerlas separadas: el día que se conecte al Brightspace real,
solo cambian esas dos URL.

> **Fuente:** [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §1;
> [`docs/ESPECIFICACION.md`](docs/ESPECIFICACION.md) §1 (hosts).

### 0.4 Cómo se entra a la API: OAuth 2.0, tokens y scopes

Brightspace no deja que cualquiera llame a su API. EduTrace tiene que demostrar quién es y qué le
permiten hacer:

- **OAuth 2.0** es un estándar de *autorización delegada*: el usuario le da permiso a una aplicación
  (EduTrace) para usar **su** cuenta de Brightspace con ciertos permisos, **sin darle su contraseña**.
  El usuario escribe su contraseña en la página de Brightspace; EduTrace solo recibe un **token**.
- Un **access token** es una credencial de vida corta que EduTrace manda en cada llamada
  (`Authorization: Bearer <token>`). Para el cliente es un texto opaco: se copia, no se interpreta.
- Un **refresh token** sirve para pedir un access token nuevo sin que el usuario vuelva a loguearse.
  En Brightspace es de **un solo uso**.
- Un **scope** es un permiso concreto, con la forma `grupo:recurso:acción`, por ejemplo
  `dropbox:folders:read` ("leer carpetas de entrega").
- Un **rol** dice sobre qué cursos puede actuar el usuario (docente en uno, estudiante en otro). Para
  que una llamada pase se necesitan **ambos**: el scope y el rol.

Hay **dos formas** de obtener un token, y el mock implementa las dos:

| | Authorization Code | Client Credentials |
|---|---|---|
| ¿Hay un usuario conectado? | Sí: inicia sesión y autoriza | No |
| ¿Como quién actúa el token? | Como ese usuario | Como un **usuario de servicio** |
| ¿Cómo prueba la app quién es? | Con un secreto compartido (`client_secret`) | Con una firma digital (un JWT firmado con su clave privada) |
| Para qué sirve en EduTrace | Que docentes y estudiantes entren con su cuenta de Brightspace | Tareas de fondo, como sincronizar listas de clase |

> **Fuente:** [`docs/02-OAUTH-AUTHORIZATION-CODE.md`](docs/02-OAUTH-AUTHORIZATION-CODE.md) §1 (qué es
> OAuth y los actores); [`docs/03-OAUTH-CLIENT-CREDENTIALS.md`](docs/03-OAUTH-CLIENT-CREDENTIALS.md) §1
> (la diferencia entre las dos concesiones);
> [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md) §1-3 (token, scopes, roles);
> [`docs/10-GLOSARIO.md`](docs/10-GLOSARIO.md).

### 0.5 Las etiquetas `[DOC]`, `[APROX]` y `[MOCK]`

Verás estas marcas en toda la documentación. Dicen **cuánto puedes confiar** en cada comportamiento:

| Etiqueta | Significa | Qué hacer con ella |
|---|---|---|
| **[DOC]** | Copiado de la documentación oficial de D2L | Puedes programar contra eso con confianza razonable |
| **[APROX]** | D2L no lo documenta o es ambiguo; el mock eligió algo razonable | **No dependas** de ese detalle exacto; verifícalo con Brightspace real |
| **[MOCK]** | Solo existe en el mock | No lo uses desde EduTrace |

> **Fuente:** [`docs/00-INDICE.md`](docs/00-INDICE.md) ("Convenciones") y
> [`docs/09-FIDELIDAD-DOC-VS-APROX.md`](docs/09-FIDELIDAD-DOC-VS-APROX.md) §1.

---

## 1. Estructura del proyecto

```
mock-brightspace/
├── app/
│   ├── main.py            arranque: crea la app, middleware de token y límite de tasa, errores
│   ├── config.py          lee las variables de entorno
│   ├── db.py              esquema SQLite, conexión por petición, formato de fechas de D2L
│   ├── errors.py          errores en formato D2L (texto) y OAuth (JSON)
│   ├── seed.py            datos de demostración (se cargan si la base está vacía)
│   ├── apps.py            registrar / listar / borrar aplicaciones OAuth
│   ├── oauth/
│   │   ├── routes.py      HTTP del servidor de autorización (login, consentimiento, token)
│   │   ├── service.py     la lógica: validar solicitudes, emitir códigos y tokens
│   │   └── pages.py       HTML de login, consentimiento y error
│   ├── security/
│   │   ├── passwords.py   PBKDF2 para contraseñas y secretos; SHA-256 para tokens guardados
│   │   ├── keys.py        clave RSA con la que el mock firma los access tokens
│   │   ├── tokens.py      emitir y verificar access tokens (JWT RS256)
│   │   ├── scopes.py      gramática de scopes y "¿alcanza este scope?"
│   │   ├── ratelimit.py   token bucket del límite de tasa
│   │   └── assertions.py  verificar la aserción JWT del flujo servidor a servidor
│   └── api/
│       ├── deps.py        dependencias comunes: conexión, quién llama, scope, versión, rol
│       ├── formats.py     convierte filas SQLite en las estructuras JSON de D2L
│       ├── common.py      leer JSON con las reglas de D2L; escribir notas
│       ├── versions.py    /d2l/api/versions/...
│       ├── users.py       whoami y users/(userId)
│       ├── enrollments.py myenrollments, usuarios de un curso, classlist
│       ├── dropbox.py     carpetas, entregas, retroalimentación
│       └── grades.py      ítems de calificación y notas
├── admin.py               línea de comandos de administración
├── tests/                 34 pruebas de punta a punta
├── docs/                  documentación técnica (empieza por 00-INDICE.md)
├── Dockerfile, docker-compose.yml, requirements*.txt
└── data/                  se crea al arrancar
```

Qué hay en `data/` y qué pasa si la borras:

| Ruta | Qué es | Si la borras… |
|---|---|---|
| `data/brightspace_mock.sqlite3` (+ `-wal`, `-shm`) | La base de datos | Se pierden usuarios, apps, entregas y notas; al arrancar se recarga la demo |
| `data/signing_key.pem` | Clave RSA con la que se firman los access tokens | Se genera una nueva: **todos los tokens emitidos dejan de servir** |
| `data/uploads/<idEntrega>/<idArchivo>` | Los archivos entregados | Las descargas de esos archivos fallan |

La carpeta `docs/` se lee en este orden: [00-INDICE](docs/00-INDICE.md) →
[01-ARQUITECTURA](docs/01-ARQUITECTURA.md) → [02-OAUTH-AUTHORIZATION-CODE](docs/02-OAUTH-AUTHORIZATION-CODE.md) →
[03-OAUTH-CLIENT-CREDENTIALS](docs/03-OAUTH-CLIENT-CREDENTIALS.md) →
[04-TOKENS-SCOPES-PERMISOS](docs/04-TOKENS-SCOPES-PERMISOS.md) → [05-REFERENCIA-API](docs/05-REFERENCIA-API.md) →
[06-MODELO-DE-DATOS](docs/06-MODELO-DE-DATOS.md) → [07-ENTREGAS-RETRO-NOTAS](docs/07-ENTREGAS-RETRO-NOTAS.md) →
[08-OPERACION-Y-PRUEBAS](docs/08-OPERACION-Y-PRUEBAS.md) →
[09-FIDELIDAD-DOC-VS-APROX](docs/09-FIDELIDAD-DOC-VS-APROX.md) → [10-GLOSARIO](docs/10-GLOSARIO.md).
[`docs/ESPECIFICACION.md`](docs/ESPECIFICACION.md) resume qué copia y qué aproxima, y explica los
flujos de uso.

> **Fuente:** [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §3 (mapa de archivos) y §6 (carpeta
> `data/`); [`docs/00-INDICE.md`](docs/00-INDICE.md) ("Cómo leerla").

---

## 2. Correrlo en tu computador

Necesitas Python 3.10 o superior.

```bash
python3 -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest                   # 34 pruebas; deben pasar todas
uvicorn app.main:create_app --factory --port 8800
```

Qué hace cada línea:

| Línea | Qué hace |
|---|---|
| `python3 -m venv .venv` | Crea un *entorno virtual*: una carpeta con sus propias librerías, para no mezclar con las del sistema |
| `source .venv/bin/activate` | Activa ese entorno en la terminal actual (hay que repetirlo en cada terminal nueva) |
| `pip install -r requirements-dev.txt` | Instala las dependencias del mock (FastAPI, uvicorn, PyJWT, cryptography, httpx, python-multipart) y `pytest` para las pruebas. SQLite no se instala: viene incluido en Python |
| `python -m pytest` | Corre las 34 pruebas de punta a punta (14 de OAuth y 20 de la API). Es opcional pero confirma que todo está bien |
| `uvicorn app.main:create_app --factory --port 8800` | Arranca el servidor en el puerto 8800 |

Detalles que conviene saber:

- **`--factory` es obligatorio.** La aplicación no existe al importar el módulo: se crea al llamar a
  `create_app()`. Sin `--factory`, uvicorn busca una variable `app` que no existe y falla. Las
  pruebas usan esta misma fábrica para crear una app nueva por prueba, sin tocar `data/`.
- **La terminal debe quedar abierta**: si la cierras, el servidor se detiene. Para dejarlo en segundo
  plano usa Docker o systemd (ver [§2](#2-correrlo-en-tu-servidor)).
- Para que **otras máquinas** lo alcancen, agrega `--host 0.0.0.0`.
- **La primera vez** crea la carpeta `data/` con la base SQLite, la clave con la que firma los tokens
  y los [datos de demostración](#3-datos-de-demostración). Después reutiliza lo que ya existe.

Comprueba que funciona:

- Versiones de la API: <http://localhost:8800/d2l/api/versions/> (no necesita token; **la barra final
  es obligatoria**).
- Documentación interactiva (solo existe en el mock): <http://localhost:8800/.mock/docs>

Para volver al estado inicial: detén uvicorn (Ctrl+C), corre `python admin.py reset` y arranca de
nuevo. `reset` borra **todo** (apps registradas, entregas y la clave de firma), así que después hay
que volver a [registrar las apps](#4-registrar-edutrace-como-aplicación).

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §2 (correrlo), §3
> (`reset`) y §4 (las pruebas); [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §4 (`create_app` y
> `--factory`) y §6 (carpeta `data/`); [`docs/05-REFERENCIA-API.md`](docs/05-REFERENCIA-API.md) §1 y §9
> (rutas de versiones y rutas solo del mock).

---

## 3. Correrlo en tu servidor

Pensado para un Ubuntu Server con un i3 y 4 GB de RAM. El mock consume unos 60 MB, así que cabe de
sobra junto a CasaOS y Crafty: no hace falta apagarlos. Lo que sí conviene es **no tener un servidor
de Minecraft prendido durante la presentación**.

### 3.1 Opción A: con Docker (CasaOS ya trae Docker)

```bash
git clone <tu-repo> mock-brightspace && cd mock-brightspace
sudo docker compose up -d --build
sudo docker compose exec brightspace-mock python admin.py register-app ...   # registrar EduTrace (ver §4)
```

Qué hace el `docker-compose.yml`:

| Configuración | Efecto |
|---|---|
| Imagen `python:3.11-slim` | Construye el contenedor con Python 3.11 |
| Puerto `8800` | Lo publica en el servidor |
| `./data` → `/data` | Los datos del servidor se montan dentro del contenedor, así **sobreviven a reinicios** |
| `restart: unless-stopped` | Arranca solo cuando arranca Docker |
| `mem_limit: 256m` | Docker lo mata si pasa de 256 MB (el mock usa ~60) |

El contenedor **ya ejecuta uvicorn** al arrancar (lo hace el `CMD` del `Dockerfile`). Por eso:

> **No** lances `uvicorn` con `docker compose exec`: ya hay uno escuchando en el 8800 y el segundo
> falla con `address already in use`. `exec` sirve para los comandos de `admin.py`.

Comandos del día a día:

| Para… | Comando |
|---|---|
| Construir y arrancar | `sudo docker compose up -d --build` |
| Ver si está corriendo | `sudo docker compose ps` |
| Ver los logs en vivo | `sudo docker compose logs -f brightspace-mock` |
| Aplicar cambios del `docker-compose.yml` | `sudo docker compose up -d` |
| Aplicar cambios del código | `sudo docker compose up -d --build` |
| Detener | `sudo docker compose down` |
| Comandos de administración | `sudo docker compose exec brightspace-mock python admin.py <comando>` |

Los archivos de `./data` los crea el contenedor como `root`: para borrarlos desde el servidor
necesitas `sudo`. La primera versión de este README no pudo probar la imagen de Docker; en el
servidor del proyecto el contenedor sí arrancó.

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §2 ("Con Docker") y §6
> (`address already in use`).

### 3.2 Opción B: sin Docker, con systemd

systemd es el sistema de Ubuntu que mantiene servicios corriendo en segundo plano y los reinicia si
fallan.

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

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §1 (variables
> `DATA_DIR`, `AUTH_BASE_URL`, `API_BASE_URL`) y §2 (systemd como alternativa a Docker para segundo
> plano); [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §4 (`--factory`).

### 3.3 Cambiar las URL cuando no es `localhost`

Si entras al mock por la IP del servidor o por un dominio, **hay que decirle su dirección real**
poniendo `AUTH_BASE_URL` y `API_BASE_URL` (en `docker-compose.yml` o en la unidad de systemd) y
reiniciando. Si no, pasan tres cosas:

1. **Servidor a servidor:** las aserciones JWT fallan por `aud` incorrecto, porque el `aud` que se
   exige es `AUTH_BASE_URL` + `/core/connect/token`. Es a propósito: Brightspace también compara
   contra su URL exacta.
2. **Paginación:** los enlaces `Next` de los listados apuntan a `localhost`.
3. **Cookie de login:** con `COOKIE_SECURE=true` sin HTTPS el login responde "La sesión del
   formulario expiró" (ver [§7](#7-si-algo-falla)).

Desde tu portátil, usa la IP del servidor en lugar de `localhost`. Si el servidor tiene firewall,
hay que abrir el puerto 8800 (por ejemplo `sudo ufw allow 8800/tcp`; este consejo es general de
Ubuntu y no viene de `docs/`).

> **Fuente:** [`docs/03-OAUTH-CLIENT-CREDENTIALS.md`](docs/03-OAUTH-CLIENT-CREDENTIALS.md) §6 ("El
> `aud` depende de `AUTH_BASE_URL`"); [`docs/05-REFERENCIA-API.md`](docs/05-REFERENCIA-API.md) (estructuras
> de paginación, `Next`); [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §1 (nota sobre
> `COOKIE_SECURE`), §5 (`<host>`) y §6.

### 3.4 HTTPS y acceso desde fuera de tu casa

Brightspace real solo funciona por HTTPS, y la parte de EduTrace es la seguridad, así que conviene
probarlo también así. Dos caminos que no requieren abrir puertos en el router:

- **Cloudflare Tunnel** (requiere un dominio en Cloudflare) o **Tailscale Funnel**: te dan una URL
  HTTPS pública que llega al puerto 8800.
- Luego pon esa URL en `AUTH_BASE_URL` y `API_BASE_URL`, y `COOKIE_SECURE=true`.

`COOKIE_SECURE=true` solo se activa cuando el mock **esté** detrás de HTTPS; sin HTTPS, el login se
rompe.

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §1 (`COOKIE_SECURE`) y
> §6; [`docs/09-FIDELIDAD-DOC-VS-APROX.md`](docs/09-FIDELIDAD-DOC-VS-APROX.md) §2 (JWKS por HTTPS);
> [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md) §5 (detrás de un proxy o túnel,
> las peticiones sin token pueden compartir cubeta del límite de tasa).

### 3.5 Reiniciar los datos de forma segura en el servidor

`admin.py reset` borra la carpeta de datos mientras el servidor puede estar usándola, y en Docker
`/data` es un punto de montaje que Python no puede borrar, así que **probablemente falle a mitad de
camino dentro del contenedor**. El procedimiento seguro:

- **Docker:** `sudo docker compose down` → `sudo rm -rf data/*` → `sudo docker compose up -d`
- **Sin Docker:** detener uvicorn (Ctrl+C) → `python admin.py reset` → arrancar uvicorn

Después hay que **volver a registrar las apps** (cambian los `client_id` y secretos) y todos los
tokens anteriores dejan de servir (la clave de firma es nueva).

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §3 ("Cómo reiniciar los
> datos de forma segura").

---

## 4. Datos de demostración

La primera vez que arranca (o después de `admin.py reset`) el mock carga datos de prueba. **Todas las
contraseñas son `Mock2026!`** (o la que pongas en `MOCK_DEMO_PASSWORD` antes de crear los datos).

### 4.1 Usuarios

| ID | Usuario | Nombre | Rol | Curso |
|---|---|---|---|---|
| 3001 | `docente1` | Ana Rojas | Instructor | 6650 Introducción a la Programación |
| 3101, 3102, 3103 | `estudiante1`, `estudiante2`, `estudiante3` | Camila Díaz, Mateo Gómez, Valentina Ruiz | Student | 6650 |
| 3002 | `docente2` | Luis Pardo | Instructor | 6651 Estructuras de Datos |
| 3104 | `estudiante4` | Samuel Torres | Student | 6651 |
| 3900 | `admin` | Admin Mock | Administrador de la organización | ve todos los cursos |
| 3950 | `svc_edutrace` | Servicio EduTrace | Usuario de servicio, **sin contraseña** | ve todos los cursos (para servidor a servidor) |

`python admin.py users` lo lista todo con la contraseña de demo.

### 4.2 Tareas del curso 6650

| ID | Nombre | Estado | Ítem de nota |
|---|---|---|---|
| 701 | Taller 1: Condicionales | abierta | 5001 (máximo 5) |
| 702 | Taller 2: Ciclos | abierta | 5002 (máximo 5) |
| 703 | Taller 3 (borrador oculto) | **oculta** | — |
| 704 | Taller 0 (cerrado) | **cerrada** | — |

`estudiante1` ya tiene una entrega (`main.cpp`) en la 701. El curso 6651 tiene una carpeta (751) y un
ítem de nota (5101).

### 4.3 Para qué sirve cada dato

| Dato | Caso que permite probar |
|---|---|
| Dos cursos con docentes distintos | Que un docente no pueda tocar el curso de otro (403) |
| Carpeta oculta (703) | Que el estudiante no la vea (404) y el docente sí |
| Carpeta cerrada (704) | Que no se pueda entregar fuera de la ventana (403) |
| Carpetas enlazadas a ítems de nota | Que publicar retroalimentación pase la nota al libro |
| Entrega de ejemplo | Que el docente vea algo sin tener que entregar antes |
| `admin` y `svc_edutrace` | Acceso a todo, para el flujo servidor a servidor |
| Usuario de servicio sin contraseña | Que nadie pueda iniciar sesión como él |

### 4.4 Dos advertencias importantes

> **Las fechas son relativas al momento de cargar los datos.** Las carpetas 701, 702 y 751 **se
> cierran 21 días después**; pasado ese plazo, entregar responde 403 ("not authorized to submit … at
> this time"). Los cursos se desactivan a los 60 días. Para renovar las fechas: reiniciar los datos
> ([§2.5](#25-reiniciar-los-datos-de-forma-segura-en-el-servidor)) o crear carpetas nuevas con
> `POST .../dropbox/folders/`.

> **Los IDs son inventados** (6650, 3101…). **EduTrace no debe tener ningún ID fijo en su código**:
> los descubre con `whoami`, `myenrollments`, etc., igual que tendrá que hacerlo con Brightspace real.

> **Fuente:** [`docs/06-MODELO-DE-DATOS.md`](docs/06-MODELO-DE-DATOS.md) §7 (todas las tablas de datos
> de demo, el "por qué" y el aviso de fechas relativas); [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md)
> §3 (`users`) y §6 (error 403 "at this time"); [`docs/01-ARQUITECTURA.md`](docs/01-ARQUITECTURA.md) §7
> (por qué los IDs son inventados).

---

## 5. Registrar EduTrace como aplicación

Antes de que EduTrace pueda pedir tokens, Brightspace tiene que **conocerlo**. En Brightspace real lo
hace un administrador desde *Manage Extensibility > OAuth 2.0*. En el mock se usa `admin.py`
(el equivalente de las *Admin Tools*).

### 5.1 Para usuarios que inician sesión (Authorization Code)

```bash
python admin.py register-app --name EduTrace \
  --redirect-uri http://localhost:8000/auth/brightspace/callback \
  --scopes "users:own_profile:read enrollment:own_enrollment:read enrollment:orgunit:read dropbox:folders:read,write grades:gradeobjects:read grades:gradevalues:read grades:own_grades:read"
```

(En el servidor con Docker: `sudo docker compose exec brightspace-mock python admin.py register-app ...`).

El comando imprime `client_id` y `client_secret`. **El secreto solo se muestra esa vez**: en la base
queda únicamente su hash. Lo que se guarda y para qué:

| Dato | Para qué |
|---|---|
| `client_id` | Identifica a la app. Es público |
| `client_secret` | Prueba que quien canjea el código es la app de verdad |
| `redirect_uri` | A dónde se devuelve al usuario con el código. **Debe ser exactamente** la que use EduTrace: una barra de más y el mock la rechaza (con una página de error, sin redirigir) |
| `scopes` | El máximo de permisos que la app podrá pedir |
| `--lifetime` | Vida del access token en segundos; entre 1800 y 72000 (por defecto 3600) |
| `--no-refresh` / `--no-consent` | Apagan los refresh tokens / la pantalla de consentimiento (por defecto ambos están activos) |

Qué permite cada scope del ejemplo:

| Scope | Para qué lo usa EduTrace | Ruta |
|---|---|---|
| `users:own_profile:read` | Saber quién inició sesión | `users/whoami` |
| `enrollment:own_enrollment:read` | Ver **mis cursos** y mi rol en cada uno | `enrollments/myenrollments/` |
| `enrollment:orgunit:read` | Ver la lista de clase de un curso | `classlist/` |
| `dropbox:folders:read,write` | Leer/crear carpetas, entregar, leer/publicar retroalimentación | `dropbox/folders/...` |
| `grades:gradeobjects:read` | Ver los ítems del libro de calificaciones | `grades/` |
| `grades:gradevalues:read` | Ver las notas de los estudiantes (docente) | `grades/(id)/values/` |
| `grades:own_grades:read` | Ver las notas propias (estudiante) | `myGradeValue` |

Cómo se escriben los scopes: `grupo:recurso:acción`, separados por **espacios**; varias acciones con
**comas sin espacios** (`read,write`); comodines con `*` (`dropbox:*:read`). El token solo lleva los
scopes que **pides al iniciar sesión**, no todos los registrados.

### 5.2 Para tareas de fondo sin usuario (Client Credentials)

```bash
python admin.py register-s2s --name "EduTrace sync" \
  --jwks-url http://localhost:8000/.well-known/jwks.json \
  --scopes "enrollment:orgunit:read dropbox:folders:read" --service-user svc_edutrace
```

Aquí **no hay secreto**: EduTrace demuestra quién es con una firma digital. Debe:

- publicar su **clave pública** en la `--jwks-url` (un JSON con `{"keys": [...]}`; Brightspace exige
  HTTPS, el mock acepta también `http://` y `file://` mientras `ALLOW_INSECURE_JWKS=true`);
- firmar cada petición de token con su **clave privada**, que nunca sale de su servidor.

El comando imprime el `aud` exacto que debe llevar la aserción. El token resultante actúa como el
`--service-user` (por defecto `svc_edutrace`).

### 5.3 Otros comandos de `admin.py`

| Comando | Qué hace |
|---|---|
| `list-apps` | Lista las apps registradas (sin secretos) |
| `delete-app <client_id>` | Borra la app, sus códigos, refresh tokens y consentimientos. Los access tokens ya emitidos siguen valiendo hasta vencer |
| `users` | Lista usuarios, rol de organización, cursos con su rol y la contraseña de demo |
| `reset` | **Borra toda la carpeta de datos** y recarga la demo (ver [§2.5](#25-reiniciar-los-datos-de-forma-segura-en-el-servidor)) |

> **Fuente:** [`docs/02-OAUTH-AUTHORIZATION-CODE.md`](docs/02-OAUTH-AUTHORIZATION-CODE.md) §2 (qué se
> registra y qué se valida); [`docs/03-OAUTH-CLIENT-CREDENTIALS.md`](docs/03-OAUTH-CLIENT-CREDENTIALS.md)
> §2 y §7 (registro, JWKS y qué construir); [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md)
> §2 (gramática de scopes); [`docs/05-REFERENCIA-API.md`](docs/05-REFERENCIA-API.md) (scope de cada
> ruta); [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §3 (tabla de `admin.py`).

---

## 6. Qué tiene que hacer el cliente de EduTrace (sin código)

Esta es la lista de piezas que debe construir el backend de EduTrace para hablar con Brightspace
(o con el mock). El paso a paso con peticiones concretas está en
[`docs/ESPECIFICACION.md`](docs/ESPECIFICACION.md), sección "Flujos de uso".

| # | Qué hacer | Por qué |
|---|---|---|
| 1 | **Dos URL configurables**: la de autorización y la de la API | En real son hosts distintos (`auth.brightspace.com` y `<universidad>.brightspace.com`); en el mock, el mismo |
| 2 | **Login:** redirigir el navegador a `/oauth2/auth` con `response_type=code`, `client_id`, `redirect_uri`, `scope` y un `state` aleatorio. Al volver, **mirar `error` antes que `code`** y **comprobar que el `state` coincide** | El `state` evita un ataque (CSRF de login): sin la comprobación, alguien podría hacer que un usuario quede logueado con la cuenta del atacante. El mock solo devuelve el `state`; compararlo es trabajo de EduTrace |
| 3 | **Canjear el código** en `POST /core/connect/token`, en `application/x-www-form-urlencoded`, con `client_id`/`client_secret` por HTTP Basic, y la **misma** `redirect_uri` | El código sirve **una sola vez** y vence en 5 minutos. Mandar JSON o recargar el callback da `invalid_request` / `invalid_grant` |
| 4 | **Guardar los tokens en el servidor**, nunca en el navegador. Leer `expires_in` | Un token "Bearer" lo puede usar quien lo tenga; la vida real puede no ser la que pediste |
| 5 | **Refrescar** con `grant_type=refresh_token`, guardando siempre el refresh token **nuevo** | Cada refresh token sirve una sola vez. Si dos peticiones refrescan a la vez, una falla: hay que permitir un solo refresco a la vez por usuario |
| 6 | **Llamar a la API** con `Authorization: Bearer <token>`. Tratar el token como **opaco** | Un **403 con `Invalid Token`** es token vencido o inválido (Brightspace no usa 401); un 403 con otro texto es falta de scope o de permiso |
| 7 | **Saber quién inició sesión** con `users/whoami` | Brightspace no documenta OpenID Connect: no hay `id_token` ni *userinfo* |
| 8 | **Respetar el límite de tasa:** leer `X-Rate-Limit-Remaining` y, ante un 429, esperar `Retry-After` | Cada app tiene una cubeta de créditos compartida por todos sus usuarios |
| 9 | **Paginar:** `PagingInfo.Bookmark` / `HasMoreItems` en unos listados y `Next` en otros | Hay dos estructuras de paginación distintas |
| 10 | **No fijar IDs** (cursos, carpetas, usuarios): descubrirlos con `whoami` y `myenrollments` | Los IDs del mock son inventados y los de Brightspace serán otros |

Las pruebas de `tests/` hacen cada uno de estos pasos contra el mock; sirven como referencia de las
peticiones exactas.

> **Fuente:** [`docs/02-OAUTH-AUTHORIZATION-CODE.md`](docs/02-OAUTH-AUTHORIZATION-CODE.md) §4 (pasos y
> validaciones), §5 (refresh de un solo uso) y §8 (checklist del cliente);
> [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md) §1 (token opaco), §5 (límite
> de tasa) y §6 (diagnóstico del 403); [`docs/05-REFERENCIA-API.md`](docs/05-REFERENCIA-API.md)
> (paginación y `whoami`); [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §4 (qué
> prueba cada test).

### Primera prueba a mano (Postman)

Para entender el flujo antes de programarlo:

1. Registra una app con redirect `http://localhost:9000/callback`.
2. Abre en el navegador `http://<host>:8800/oauth2/auth?response_type=code&client_id=<ID>&redirect_uri=http://localhost:9000/callback&scope=users:own_profile:read%20enrollment:own_enrollment:read&state=prueba123`.
3. Inicia sesión con `estudiante1` / `Mock2026!` y autoriza.
4. La página de destino **no cargará, y es normal** (no hay nada en el puerto 9000). Copia el `code`
   de la barra de direcciones.
5. En Postman: `POST http://<host>:8800/core/connect/token`, *Basic Auth* con el `client_id` y el
   secreto, cuerpo `x-www-form-urlencoded` con `grant_type=authorization_code`, `code` y `redirect_uri`.
6. Usa el `access_token` como *Bearer Token* en `/d2l/api/lp/1.49/users/whoami`.

`<host>` es `localhost` si el mock corre en tu máquina, o la IP del servidor. La `redirect_uri` usa
siempre `localhost` porque es una dirección a la que va **tu navegador**, no el mock.

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §5 (Postman, con la
> tabla "Para ver errores a propósito").

---

## 7. Variables de entorno

Se configuran al arrancar (en `docker-compose.yml`, en la unidad de systemd o en la terminal).

| Variable | Por defecto | Para qué | Cuándo cambiarla |
|---|---|---|---|
| `DATA_DIR` | `./data` (Docker: `/data`) | Base SQLite, archivos entregados y clave de firma | Rara vez |
| `AUTH_BASE_URL` / `API_BASE_URL` | `http://localhost:8800` | URL pública del mock; la primera define el `aud` de las aserciones y la segunda arma los enlaces `Next` | Siempre que accedas por otra dirección |
| `MOCK_DEMO_PASSWORD` | `Mock2026!` | Contraseña de los usuarios de demo | Solo tiene efecto al **crear** los datos |
| `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_WINDOW_S` | `300` / `60` | Tamaño de la cubeta y tiempo de rellenado del límite de tasa | Para probar el 429 (ponla en 5) |
| `PAGE_SIZE` | `100` | Tamaño de página de los listados | Para probar la paginación (ponla en 1) |
| `CORE_SCOPE_GRANTS_ALL` | `false` | Si `core:*:*` abre todas las rutas | Normalmente nunca |
| `ALLOW_INSECURE_JWKS` | `true` | Permite JWKS por `http://` y `file://` | `false` para simular la exigencia de HTTPS de Brightspace |
| `MAX_JSON_BYTES` | 1 MB | Tamaño máximo de un JSON | — |
| `MAX_UPLOAD_BYTES` | 50 MB | Tamaño máximo de una entrega (en D2L, ~490 MB) | Si tu servidor tiene poco disco |
| `REFRESH_TOKEN_TTL_S` | 30 días | Vida del refresh token | Para probar refresh tokens vencidos |
| `COOKIE_SECURE` | `false` | Cookie de sesión del login solo por HTTPS | `true` **solo** detrás de HTTPS |
| `LP_VERSIONS` / `LE_VERSIONS` | `1.46…1.49` / `1.79…1.82` | Versiones de la API que acepta | Si quieres simular otra versión |
| `TENANT_ID` | un UUID fijo | Claim `tenantid` del token | No hace falta |

Fijos en el código: la vida del código de autorización (300 s) y de la sesión de login (8 h).

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §1 (tabla completa y la
> nota sobre `COOKIE_SECURE`); [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md)
> §2 (`core:*:*`), §4 (versiones) y §5 (límite de tasa).

---

## 8. Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `connect ECONNREFUSED 127.0.0.1:8800` | El mock no está corriendo, o corre en otro puerto u otra máquina | Arrancar uvicorn y dejar la terminal abierta; con Docker, `docker compose ps`; usar la IP correcta |
| `address already in use` | Ya hay algo en el puerto (en Docker, el uvicorn del propio contenedor) | `sudo ss -tlnp \| grep 8800`; en Docker no arranques uvicorn a mano |
| `Attribute "app" not found` | Faltó `--factory` | `uvicorn app.main:create_app --factory ...` |
| `ModuleNotFoundError` | Entorno virtual sin activar o dependencias sin instalar | Activar `.venv` y `pip install -r requirements.txt` |
| 404 con cuerpo vacío | Falta la barra final, versión no soportada, ID no numérico o ruta mal escrita | Comparar con [`docs/05-REFERENCIA-API.md`](docs/05-REFERENCIA-API.md) |
| `403 Invalid Token` | Token vencido, mal copiado, sin `Bearer`, o firmado con una clave anterior (se reinició `data/`) | Pedir un token nuevo |
| `403 Insufficient scope` | El token no tiene ese scope | Revisar los scopes que **pediste**, no los registrados |
| Página "No se puede continuar" en `/oauth2/auth` | `client_id` o `redirect_uri` no coinciden con lo registrado | `admin.py list-apps` y comparar carácter por carácter |
| `invalid_grant` al canjear el código | Código usado (recargaste), vencido o `redirect_uri` distinta | Repetir desde `/oauth2/auth` |
| `invalid_client` con "aserción inválida" | Casi siempre un `aud` incorrecto | Debe ser `AUTH_BASE_URL` + `/core/connect/token` |
| "La sesión del formulario expiró" | La cookie no llegó: alternaste entre `localhost` y `127.0.0.1`, cookies bloqueadas, o `COOKIE_SECURE=true` sin HTTPS | Usar siempre el mismo host; revisar `COOKIE_SECURE` |
| Los enlaces `Next` apuntan a `localhost` | `API_BASE_URL` sin actualizar | Ponerle la dirección real y reiniciar |
| Entregar da 403 "at this time" | Pasaron más de 21 días y la carpeta se cerró | Reiniciar los datos o crear otra carpeta |
| Error 500 | Un fallo del mock | `docker compose logs` o la terminal de uvicorn muestran el error completo |

> **Fuente:** [`docs/08-OPERACION-Y-PRUEBAS.md`](docs/08-OPERACION-Y-PRUEBAS.md) §6 (tabla de solución
> de problemas); [`docs/04-TOKENS-SCOPES-PERMISOS.md`](docs/04-TOKENS-SCOPES-PERMISOS.md) §6 (diagnóstico
> de un 403); [`docs/02-OAUTH-AUTHORIZATION-CODE.md`](docs/02-OAUTH-AUTHORIZATION-CODE.md) §6 (errores del
> flujo).

---

## 9. Qué tan fiel es al Brightspace real

El mock solo es útil si sabes en qué puedes confiar. Resumen:

- **Copia fiel de la documentación de D2L [DOC]:** las dos concesiones OAuth y sus formatos, el 403 con
  `Invalid Token`, el límite de tasa con sus cuatro encabezados, el formato de fechas, `RichText`, las
  rutas implementadas con sus scopes, la entrega `multipart/mixed` y las estructuras de carpetas,
  entregas, retroalimentación y notas.
- **Aproximado [APROX]:** la forma exacta de la paginación, los campos de la respuesta del token, los
  valores del límite de tasa, las versiones de la API, los permisos por rol, que publicar
  retroalimentación con puntaje pase la nota al libro, y el cálculo de la nota final.
- **Solo del mock [MOCK]:** las páginas de login y consentimiento, `/.mock/docs`, `/.mock/jwks`.
- **No existe:** LTI 1.3, carga resumible, rúbricas, grupos, entregas de solo texto, revocación de
  tokens, PKCE, OpenID Connect.

Si algún día hay acceso a un Brightspace real, lo primero que hay que verificar, en orden: la
paginación, si publicar retroalimentación pasa la nota al libro, los campos de la respuesta del
token, si `core:*:*` abre rutas con scope específico, la versión más reciente de `lp` y `le`,
`Authorization` vs `Authentication`, y si se acepta PKCE.

> **Fuente:** [`docs/09-FIDELIDAD-DOC-VS-APROX.md`](docs/09-FIDELIDAD-DOC-VS-APROX.md) §2-6 (tablas de
> fidelidad, lo que no existe y qué verificar primero); [`docs/ESPECIFICACION.md`](docs/ESPECIFICACION.md)
> (qué copia y qué aproxima).

---
