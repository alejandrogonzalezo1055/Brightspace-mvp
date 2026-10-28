# 10 · Glosario

**Access token** — Credencial de vida corta que el cliente manda en cada llamada a la API
(`Authorization: Bearer ...`). En el mock es un JWT; para el cliente debe ser un texto opaco.

**Aserción JWT (client assertion)** — JWT que una app firma con su clave privada para demostrar
quién es en el flujo Client Credentials. Reemplaza al `client_secret`.

**`aud` (audience)** — Claim que dice para quién es un JWT. En la aserción debe ser la URL exacta
del endpoint de token; así una aserción para otro servicio no sirve aquí.

**`azp` (authorized party)** — Claim del access token con el `client_id` de la app que lo pidió.
El mock lo usa para la cubeta del límite de tasa.

**Authorization Code** — Concesión OAuth en la que el usuario inicia sesión y autoriza, el cliente
recibe un código por el navegador y lo canjea por tokens por el canal de servidor a servidor.

**Back-channel / front-channel** — Comunicación directa servidor a servidor (segura) vs
comunicación que pasa por el navegador (visible y manipulable).

**Base64url** — Variante de base64 que se puede poner en URL (usa `-` y `_`, sin `=`). Es la
codificación de las partes de un JWT. Codificar no es cifrar: cualquiera lo lee.

**Bearer** — "Portador": quien tenga el token puede usarlo. Por eso los tokens se guardan en el
servidor y solo viajan por HTTPS.

**Bookmark** — Marcador de paginación de D2L: un valor opaco que se manda en `?bookmark=` para
pedir la página siguiente.

**Boundary** — Cadena que separa las partes de un cuerpo `multipart`.

**Client Credentials** — Concesión OAuth sin usuario: la app se autentica a sí misma y actúa como
un usuario de servicio.

**`client_id` / `client_secret`** — Identificador público de una app registrada y su contraseña.
El secreto nunca va en el frontend ni en el repositorio.

**Claim** — Cada dato dentro del contenido de un JWT (`sub`, `exp`, `scope`…).

**Consentimiento** — Pantalla en la que el usuario autoriza a una app a usar su cuenta con ciertos
scopes.

**`core:*:*`** — Scope especial de D2L de respaldo para acciones sin scope específico.

**CSRF (Cross-Site Request Forgery)** — Ataque en que otra página hace que tu navegador envíe una
petición a un sitio donde tienes sesión. Se previene con tokens que la otra página no puede leer
(`state` en OAuth; token de doble envío en los formularios del mock).

**D2L** — Desire2Learn, la empresa que hace Brightspace.

**D2LID** — Tipo de identificador de D2L: entero positivo de 64 bits. A veces viaja como string.

**Dropbox (carpeta de entrega)** — Lo que en Brightspace equivale a una tarea donde los
estudiantes suben archivos. En la interfaz en español aparece como "Actividades" o "Carpetas de
entrega".

**`EntityDropbox`** — Estructura de D2L con todas las entregas, el estado y la retroalimentación de
**un** estudiante (o grupo) en **una** carpeta.

**Grade object (ítem de calificación)** — Una columna del libro de calificaciones.

**Grade value** — La nota de un estudiante en un ítem.

**`iss` (issuer)** — Claim de quién emitió un JWT.

**JWKS (JSON Web Key Set)** — Documento JSON con una o varias claves públicas, cada una con su
`kid`. Se publica en una URL para que otros verifiquen firmas.

**JWT (JSON Web Token)** — Token en tres partes `encabezado.contenido.firma`, cada una en
base64url. La firma permite verificar que nadie lo alteró.

**`jti` (JWT ID)** — Identificador único de un JWT. Sirve para rechazar repeticiones.

**`kid` (key ID)** — Identificador de la clave con que se firmó un JWT, para buscarla en el JWKS.

**LE / LP** — Productos de la API de Brightspace: Learning Environment (carpetas, notas, lista de
clase) y Learning Platform (usuarios, inscripciones). Cada uno tiene su número de versión.

**LTI 1.3** — Estándar para integrar herramientas externas dentro de un LMS (abrir EduTrace desde
dentro de un curso de Brightspace). No está en el mock.

**Mock** — Imitación de un sistema real para poder probar contra ella.

**`multipart/mixed`** — Tipo de cuerpo HTTP con varias partes de distinto tipo. Brightspace lo usa
para entregar archivos con un comentario JSON.

**`nbf` / `exp` / `iat`** — Claims de tiempo: no antes de, vence en, emitido en (segundos Unix).

**OAuth 2.0** — Estándar de autorización delegada (RFC 6749): una app obtiene permiso para usar la
cuenta de un usuario sin conocer su contraseña.

**Org unit (unidad organizacional)** — En Brightspace, todo nodo de la estructura: la
organización, facultades, cursos, secciones. Cada uno tiene un `OrgUnitId`.

**PBKDF2** — Algoritmo para guardar contraseñas: aplica un hash muchas veces con una sal para que
adivinar sea lento.

**PKCE** — Extensión de OAuth que protege el código con un secreto efímero del cliente. D2L no la
documenta.

**Rate limit / token bucket** — Límite de llamadas por tiempo. En el token bucket, cada llamada
gasta créditos de una cubeta que se rellena gradualmente.

**`redirect_uri`** — URL de EduTrace a la que Brightspace devuelve al usuario con el código. Debe
coincidir exactamente con la registrada.

**Refresh token** — Credencial de vida larga para pedir un nuevo access token sin que el usuario
vuelva a iniciar sesión. En Brightspace es de un solo uso.

**`RichText` / `RichTextInput`** — Formatos de D2L para texto con formato: `{Text, Html}` al leer,
`{Content, Type}` al escribir.

**RS256 / ES256** — Algoritmos de firma con clave pública: RSA o curva elíptica, con SHA-256.

**Scope** — Permiso concreto que se le da a un token, con forma `grupo:recurso:acción`.

**Servidor de autorización / de recursos** — El que emite tokens (login) y el que tiene los datos
(API). En Brightspace son hosts distintos.

**`state`** — Valor aleatorio que el cliente manda al iniciar el login y comprueba al volver.
Previene CSRF de login.

**`sub` (subject)** — Claim con el sujeto del token: el usuario (o el `client_id` en una aserción).

**Usuario de servicio** — Usuario no humano con el que actúa una app en Client Credentials.

**Valence** — Nombre de la API REST de Brightspace.

**WAL** — Modo de SQLite que permite leer mientras otro escribe. Crea los archivos `-wal` y `-shm`
junto a la base.
