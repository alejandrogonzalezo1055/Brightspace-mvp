# Documentación técnica del mock de Brightspace

Esta carpeta explica **cómo funciona por dentro** el mock de Brightspace (FastAPI + SQLite) que se
construyó para probar la integración de EduTrace con Brightspace. Complementa al `README.md`
(cómo correrlo) y a `docs/ESPECIFICACION.md` (qué se copió de D2L): aquí está el **por qué** y el
**cómo** de cada pieza.

> Esta documentación describe la versión del mock que se entregó en `mock-brightspace.zip`
> (34 pruebas). Si tú o alguien más modificó el código después, puede haber diferencias.

## Cómo leerla

Si no sabes por dónde empezar, sigue este orden:

| # | Archivo | Qué responde | Léelo si… |
|---|---|---|---|
| 1 | [01-ARQUITECTURA.md](01-ARQUITECTURA.md) | Qué piezas tiene el mock, qué hace cada archivo y qué le pasa a una petición desde que llega hasta que sale | Quieres el mapa general antes de entrar en detalle |
| 2 | [02-OAUTH-AUTHORIZATION-CODE.md](02-OAUTH-AUTHORIZATION-CODE.md) | El login con usuario: paso a paso, qué valida el mock en cada paso, refresh tokens | Vas a programar el login de EduTrace con Brightspace |
| 3 | [03-OAUTH-CLIENT-CREDENTIALS.md](03-OAUTH-CLIENT-CREDENTIALS.md) | El flujo servidor a servidor con aserción JWT y JWKS | Vas a sincronizar datos sin un usuario conectado |
| 4 | [04-TOKENS-SCOPES-PERMISOS.md](04-TOKENS-SCOPES-PERMISOS.md) | Cómo es el access token, cómo se verifica, cómo funcionan scopes, roles y el límite de tasa | Te sale un 403 y no sabes por qué |
| 5 | [05-REFERENCIA-API.md](05-REFERENCIA-API.md) | Cada ruta: parámetros, quién puede llamarla, respuesta y errores | Necesitas saber exactamente qué mandar y qué recibir |
| 6 | [06-MODELO-DE-DATOS.md](06-MODELO-DE-DATOS.md) | Tablas SQLite, cómo se convierten en el JSON de D2L, datos de demostración | Quieres entender de dónde salen los datos |
| 7 | [07-ENTREGAS-RETRO-NOTAS.md](07-ENTREGAS-RETRO-NOTAS.md) | El ciclo de una tarea: carpeta → entrega `multipart/mixed` → retroalimentación → nota | Vas a mover entregas o retroalimentación entre EduTrace y Brightspace |
| 8 | [08-OPERACION-Y-PRUEBAS.md](08-OPERACION-Y-PRUEBAS.md) | Variables de entorno, `admin.py`, Docker, las 34 pruebas, Postman y errores comunes | Lo vas a correr, desplegar o depurar |
| 9 | [09-FIDELIDAD-DOC-VS-APROX.md](09-FIDELIDAD-DOC-VS-APROX.md) | Qué es copia fiel de D2L, qué es aproximación y qué falta | Vas a confiar en un comportamiento para tu código |
| 10 | [10-GLOSARIO.md](10-GLOSARIO.md) | Definiciones de todos los términos | Una palabra no te queda clara |

## La idea en un párrafo

El mock **imita la interfaz pública de Brightspace**: las mismas URL, los mismos parámetros, los
mismos formatos JSON, los mismos códigos de error y el mismo flujo OAuth 2.0 que documenta D2L. No
imita su interior (base de datos, permisos configurables, interfaz web). La regla de diseño fue:
**si tu cliente funciona contra el mock, debería funcionar contra Brightspace real**. Por eso, donde
la documentación de D2L era ambigua, el mock eligió el comportamiento **más estricto**: así un
cliente que pasa aquí no se rompe allá por haberse apoyado en algo permisivo.

## Convenciones de esta documentación

- **[DOC]**: comportamiento copiado de la documentación oficial de D2L.
- **[APROX]**: comportamiento que D2L no documenta; el mock eligió uno razonable.
- **[MOCK]**: algo que solo existe en el mock (no lo busques en Brightspace).
- Las rutas se escriben como en la documentación de D2L: `(version)`, `(orgUnitId)`, etc. son
  partes variables. Ejemplo real: `/d2l/api/le/1.82/6650/dropbox/folders/`.
- Los ejemplos de peticiones y respuestas HTTP son ilustrativos; los valores (IDs, fechas, tokens)
  cambian en tu instalación.
