# 05 · Referencia de la API

Todas las rutas que implementa el mock, con su scope, quién puede llamarlas, parámetros, respuesta
y errores. Los ejemplos usan los datos de demostración (`06-MODELO-DE-DATOS.md`).

## Reglas comunes a todas las rutas `/d2l/api/...`

- **Autenticación**: `Authorization: Bearer <access_token>`, salvo las rutas de versiones.
- **Versión**: `lp` en 1.46–1.49 y `le` en 1.79–1.82 (configurable). Otra → 404.
- **Barra final**: se escribe **exactamente** como aparece aquí. `/folders/` y `/folders` son
  rutas distintas; la que no existe da 404.
- **IDs en la ruta**: deben ser enteros. `/abc/` → 404.
- **Cuerpos JSON**: `Content-Type: application/json` (si no: 415), máximo 1 MB (si no: 413), JSON
  válido (si no: 400 `Invalid JSON`).
- **Respuestas de error**: texto plano, a veces vacío. Ver `04-TOKENS-SCOPES-PERMISOS.md`.
- **Fechas** (`UTCDateTime`): `yyyy-MM-ddTHH:mm:ss.fffZ`, siempre con 3 decimales y `Z`.
  Ejemplo: `2026-11-30T23:59:00.000Z`. Al enviar fechas, cualquier otro formato → 400.
- **Parámetros de query desconocidos**: se ignoran.
- **Booleanos en query** (`isActive`, `activeOnly`, `isGraded`…): solo `true` o `false`; otro → 400.
- **Encabezados de límite de tasa** en todas las respuestas (ver 04).

### Estructuras de paginación [APROX: forma no verificada en la doc pública]

**`Api.PagedResultSet`** (rutas de `lp`):

```json
{
  "PagingInfo": { "Bookmark": "6650", "HasMoreItems": true },
  "Items": [ ... ]
}
```

Siguiente página: repetir la petición con `?bookmark=<Bookmark>`. Cuando `HasMoreItems` es
`false`, `Bookmark` viene vacío.

**`Api.ObjectListPage`** (algunas rutas de `le`):

```json
{
  "Next": "http://localhost:8800/d2l/api/le/1.82/6650/classlist/paged/?bookmark=3102",
  "Objects": [ ... ]
}
```

Siguiente página: hacer GET a la URL de `Next` tal cual. Cuando es `null`, no hay más.

`Next` se arma con `API_BASE_URL`: si accedes al mock por otra dirección y no la actualizaste, la
URL de `Next` apuntará a `localhost`.

Tamaño de página: `PAGE_SIZE` (100 por defecto).

---

## 1. Versiones (anónimas) [DOC]

### `GET /d2l/api/versions/`

```json
[
  { "ProductCode": "lp", "LatestVersion": "1.49", "SupportedVersions": ["1.46", "1.47", "1.48", "1.49"] },
  { "ProductCode": "le", "LatestVersion": "1.82", "SupportedVersions": ["1.79", "1.80", "1.81", "1.82"] }
]
```

### `GET /d2l/api/(lp|le)/versions/`

Un solo objeto como los de arriba. Otro producto → 404.

### `GET /d2l/api/(lp|le)/versions/(version)`

```json
{ "Supported": true, "LatestVersion": "1.49" }
```

### `POST /d2l/api/versions/check`

Cuerpo: un arreglo de `{"ProductCode": "...", "Version": "..."}`.

```json
{
  "Supported": false,
  "Versions": [
    { "ProductCode": "le", "Version": "1.82", "Supported": true,  "LatestVersion": "1.82" },
    { "ProductCode": "lp", "Version": "9.99", "Supported": false, "LatestVersion": "1.49" }
  ]
}
```

`Supported` general es `false` si alguno no está soportado. Cuerpo que no sea arreglo o ítems sin
`ProductCode`/`Version` → 400.

---

## 2. Usuarios (`lp`)

### `GET /d2l/api/lp/(version)/users/whoami`

- **Scope**: `users:profile:read` **o** `users:own_profile:read` [DOC]
- **Quién**: cualquier usuario con token

```json
{
  "Identifier": "3101",
  "FirstName": "Camila",
  "LastName": "Díaz",
  "UniqueName": "estudiante1",
  "ProfileIdentifier": "Xk2...",
  "Pronouns": ""
}
```

Notar que `Identifier` es **string** aunque represente un número [DOC]. Es la forma de saber
quién inició sesión.

### `GET /d2l/api/lp/(version)/users/(userId)`

- **Scope**: `users:userdata:read` [DOC]
- **Quién** [APROX]: admin/servicio → cualquiera; docente → usuarios de sus cursos; cualquiera → sí mismo

```json
{
  "OrgId": 6606,
  "UserId": 3101,
  "FirstName": "Camila",
  "MiddleName": null,
  "LastName": "Díaz",
  "UserName": "estudiante1",
  "ExternalEmail": "camila.diaz@uni.example",
  "OrgDefinedId": "20261001",
  "UniqueIdentifier": "estudiante1",
  "Activation": { "IsActive": true },
  "DisplayName": "Camila Díaz",
  "LastAccessedDate": "2026-10-21T05:30:00.000Z",
  "Pronouns": "",
  "FirstLoginDate": null
}
```

| Error | Causa |
|---|---|
| 404 | No existe o está inactivo |
| 403 `Not authorized to view this user` | No compartes curso con él |

[MOCK] `LastAccessedDate` es la fecha de creación (el mock no registra accesos) y
`FirstLoginDate` siempre es `null`.

---

## 3. Inscripciones y lista de clase

### `GET /d2l/api/lp/(version)/enrollments/myenrollments/`

- **Scope**: `enrollment:own_enrollment:read` [DOC]
- **Quién**: cualquier usuario; devuelve **sus** cursos
- **Query**: `orgUnitTypeId` (3 = curso), `isActive`, `canAccess`, `bookmark`
- **Respuesta**: `PagedResultSet` de `MyOrgUnitInfo`

```json
{
  "PagingInfo": { "Bookmark": "", "HasMoreItems": false },
  "Items": [
    {
      "OrgUnit": {
        "Id": 6650,
        "Type": { "Id": 3, "Code": "Course Offering", "Name": "Course Offering" },
        "Name": "Introducción a la Programación (2026-2)",
        "Code": "IP-2026-2",
        "HomeUrl": "/d2l/home/6650",
        "ImageUrl": null
      },
      "Access": {
        "IsActive": true,
        "StartDate": "2026-08-22T05:30:00.000Z",
        "EndDate": "2026-12-20T05:30:00.000Z",
        "CanAccess": true,
        "ClasslistRoleName": "Student",
        "LISRoles": ["urn:lti:role:ims/lis/Learner"],
        "LastAccessed": null
      },
      "PinDate": null
    }
  ]
}
```

Para EduTrace, **esta es la ruta que reemplaza a "mis grupos"**: de aquí salen los cursos y, con
`ClasslistRoleName`, si el usuario es docente o estudiante en cada uno.

[APROX] `HomeUrl`, `LISRoles` y `CanAccess` (= curso activo) son aproximados. El mock no devuelve
la unidad "organización" ni departamentos, solo los cursos donde hay inscripción.

### `GET /d2l/api/lp/(version)/enrollments/orgUnits/(orgUnitId)/users/`

- **Scope**: `enrollment:orgunit:read` [DOC]
- **Quién**: STAFF del curso
- **Query**: `roleId` (109 docente, 110 estudiante), `isActive`, `bookmark`
- **Respuesta**: `PagedResultSet` de `OrgUnitUser`

```json
{
  "PagingInfo": { "Bookmark": "", "HasMoreItems": false },
  "Items": [
    {
      "User": {
        "Identifier": "3101",
        "DisplayName": "Camila Díaz",
        "EmailAddress": "camila.diaz@uni.example",
        "OrgDefinedId": "20261001",
        "ProfileBadgeUrl": null,
        "ProfileIdentifier": "Xk2..."
      },
      "Role": { "Id": 110, "Code": "Student", "Name": "Student" }
    }
  ]
}
```

[APROX] La forma de `User` (bloque `User.User`) se tomó de conocimiento previo.

### `GET /d2l/api/le/(version)/(orgUnitId)/classlist/`

- **Scope**: `enrollment:orgunit:read` [DOC]
- **Quién**: MEMBERS del curso
- **Respuesta**: arreglo (sin paginar) de `ClasslistUser`, con docentes y estudiantes activos

```json
[
  {
    "Identifier": "3101",
    "ProfileIdentifier": "Xk2...",
    "DisplayName": "Camila Díaz",
    "Username": "estudiante1",
    "OrgDefinedId": "20261001",
    "Email": "camila.diaz@uni.example",
    "FirstName": "Camila",
    "LastName": "Díaz",
    "RoleId": 110,
    "LastAccessed": null,
    "IsOnline": false,
    "ClasslistRoleDisplayName": "Student",
    "Pronouns": null
  }
]
```

Si quien llama es estudiante, `Username`, `OrgDefinedId`, `Email`, `RoleId` y `LastAccessed` van
en `null` [APROX].

D2L recomienda la versión paginada porque esta no tiene límite.

### `GET /d2l/api/le/(version)/(orgUnitId)/classlist/paged/`

- Igual que la anterior, pero `ObjectListPage`.
- **Query**: `roleId`, `searchTerm` (busca en nombre, apellido, usuario y código), `onlyShowShownInGrades` (se valida pero no filtra [MOCK]), `bookmark`.

---

## 4. Carpetas de entrega (dropbox)

Base: `/d2l/api/le/(version)/(orgUnitId)/dropbox/folders/`

### Estructura `DropboxFolder` [DOC]

```json
{
  "Id": 701,
  "CategoryId": null,
  "Name": "Taller 1: Condicionales",
  "CustomInstructions": { "Text": "Sube tu archivo main.cpp.", "Html": null },
  "Attachments": [],
  "TotalFiles": 1,
  "UnreadFiles": 1,
  "FlaggedFiles": 0,
  "TotalUsers": 3,
  "TotalUsersWithSubmissions": 1,
  "TotalUsersWithFeedback": 0,
  "Availability": {
    "StartDate": "2026-10-14T05:30:00.000Z",
    "EndDate": "2026-11-11T05:30:00.000Z",
    "StartDateAvailabilityType": null,
    "EndDateAvailabilityType": null
  },
  "GroupTypeId": null,
  "DueDate": "2026-11-04T05:30:00.000Z",
  "DisplayInCalendar": false,
  "Assessment": { "ScoreDenominator": 100.0, "Rubrics": [] },
  "NotificationEmail": null,
  "IsHidden": false,
  "LinkAttachments": [],
  "ActivityId": null,
  "IsAnonymous": false,
  "DropboxType": 2,
  "SubmissionType": 0,
  "CompletionType": 0,
  "SubmissionRule": "AllSubmissions",
  "GradeItemId": 5001,
  "AllowOnlyUsersWithSpecialAccess": false
}
```

| Campo | Significado |
|---|---|
| `Total*`, `UnreadFiles`, `FlaggedFiles` | Conteos. **-1** si quien llama no puede verlos (estudiantes) [DOC] |
| `Availability` | Ventana en que se puede entregar. `null` si no tiene fechas |
| `DueDate` | Fecha límite "oficial". Entregar después es posible mientras la ventana siga abierta |
| `Assessment.ScoreDenominator` | Sobre cuánto se califica en la carpeta (aquí, 100) |
| `DropboxType` | 1 grupal, 2 individual [DOC]. El mock solo soporta 2 |
| `SubmissionType` | 0 archivo, 1 texto, 2 en papel, 3 observado, 4 archivo o texto [DOC] |
| `CompletionType` | 0 al entregar, 1 en la fecha límite, 2 manual, 3 al evaluar [DOC] |
| `SubmissionRule` | `AllSubmissions`, `OnlyOneSubmission`, `OverwriteSubmissions` [APROX: valores no verificados] |
| `GradeItemId` | Ítem del libro de calificaciones enlazado. Ver `07-ENTREGAS-RETRO-NOTAS.md` |

[APROX] `ActivityId` siempre `null`; `Attachments` y `LinkAttachments` siempre vacíos (el mock no
maneja adjuntos de carpeta).

### `GET .../dropbox/folders/`

- **Scope**: `dropbox:folders:read` · **Quién**: MEMBERS
- **Respuesta**: arreglo de `DropboxFolder` (sin paginar [DOC]). Los estudiantes no ven las ocultas.

### `GET .../dropbox/folders/(folderId)`

- **Scope**: `dropbox:folders:read` · **Quién**: MEMBERS
- 404 si no existe en ese curso, o si está oculta y quien pide es estudiante.

### `POST .../dropbox/folders/`

- **Scope**: `dropbox:folders:write` · **Quién**: STAFF
- **Cuerpo**: `DropboxFolderUpdateData` [DOC]
- **Respuesta**: 200 con el `DropboxFolder` creado

```json
{
  "Name": "Taller 4",
  "CustomInstructions": { "Content": "<p>Sube <b>main.cpp</b></p>", "Type": "Html" },
  "Availability": { "StartDate": "2026-01-01T00:00:00.000Z", "EndDate": "2030-01-01T00:00:00.000Z" },
  "DueDate": "2029-12-31T23:59:00.000Z",
  "IsHidden": false,
  "Assessment": { "ScoreDenominator": 10 },
  "DropboxType": 2,
  "SubmissionType": 0,
  "CompletionType": 0,
  "GradeItemId": 5002
}
```

Validaciones (todas → 400):

| Campo | Regla |
|---|---|
| `Name` | Obligatorio al crear; texto no vacío |
| `CustomInstructions` | `RichTextInput` (`{"Content", "Type": "Text"\|"Html"}`); también se acepta `{"Text", "Html"}` |
| `Availability.StartDate/EndDate`, `DueDate` | Formato `UTCDateTime` exacto |
| `DisplayInCalendar`, `IsHidden`, `IsAnonymous`, `AllowOnlyUsersWithSpecialAccess` | `true`/`false` |
| `NotificationEmail` | Texto |
| `Assessment.ScoreDenominator` | Número positivo. `Rubrics` con elementos → no soportado |
| `DropboxType` | 1 o 2; **1 (grupal) no soportado**; `GroupTypeId` presente → no soportado |
| `SubmissionType` | 0 a 4 |
| `CompletionType` | 0 a 3 |
| `SubmissionRule` | Uno de los tres valores |
| `GradeItemId` | Debe existir en ese curso |
| `CategoryId` | No soportado |

Con `Type: "Html"`, el mock guarda el HTML y deriva el `Text` quitando las etiquetas.

### `PUT .../dropbox/folders/(folderId)`

- **Scope**: `dropbox:folders:write` · **Quién**: STAFF
- Mismo cuerpo, **parcial**: un campo ausente o en `null` **conserva su valor** [DOC]. Consecuencia:
  por API no se puede "borrar" una fecha poniéndola en `null`.
- **Respuesta**: 200 con la carpeta actualizada.

---

## 5. Entregas

### Estructura `EntityDropbox` [DOC]

Una por estudiante, con todas sus entregas en esa carpeta:

```json
{
  "Entity": { "EntityId": 3101, "EntityType": "User", "DisplayName": "Camila Díaz" },
  "Status": 1,
  "Feedback": null,
  "Submissions": [
    {
      "Id": 1,
      "SubmittedBy": { "Id": "3101", "DisplayName": "Camila Díaz" },
      "SubmissionDate": "2026-10-21T05:30:00.000Z",
      "Comment": { "Text": "Primera versión del taller.", "Html": null },
      "Files": [
        { "FileId": 1, "FileName": "main.cpp", "Size": 112, "isRead": false, "isFlagged": false }
      ]
    }
  ],
  "CompletionDate": null
}
```

`Status` [DOC]: 0 sin entregar, 1 entregado, 2 retroalimentación en borrador, 3 publicada. Ver
`07-ENTREGAS-RETRO-NOTAS.md` para cómo se calcula.

Notar las minúsculas en `isRead` e `isFlagged`: así aparecen en la documentación de D2L.

### `GET .../folders/(folderId)/submissions/`

- **Scope**: `dropbox:folders:read` · **Quién**: STAFF
- **Respuesta**: arreglo de `EntityDropbox`, uno por **cada estudiante activo** del curso, haya
  entregado o no [APROX].

### `GET .../folders/(folderId)/submissions/paged/`

- Igual, como `ObjectListPage`. **Query**: `bookmark`, `activeOnly`.

### `GET .../folders/(folderId)/submissions/mysubmissions/`

- **Scope**: `dropbox:folders:read` · **Quién**: STUDENT
- **Respuesta**: arreglo con **un** `EntityDropbox` (el propio) [APROX: forma]. La retroalimentación
  solo aparece si está publicada.

### `GET .../folders/(folderId)/submissions/user/(userId)`

- **Scope**: `dropbox:folders:read` · **Quién**: STAFF
- **Respuesta**: arreglo con un `EntityDropbox`. 404 si el usuario no es estudiante del curso.

### `POST .../folders/(folderId)/submissions/mysubmissions/`

- **Scope**: `dropbox:folders:write` · **Quién**: STUDENT
- **Cuerpo**: `multipart/mixed` (ver `07-ENTREGAS-RETRO-NOTAS.md` para el formato exacto)
- **Respuesta**: **200 sin cuerpo** [DOC]. Para saber el ID de la entrega, consulta
  `mysubmissions` después.

| Error | Causa |
|---|---|
| 403 | Quien llama no es estudiante del curso; carpeta fuera de su ventana; ya entregó y la regla es `OnlyOneSubmission` |
| 404 | Carpeta inexistente u oculta |
| 405 | La carpeta no acepta archivos (`SubmissionType` distinto de 0 o 4) |
| 415 | `Content-Type` no es `multipart/mixed` |
| 413 | Cuerpo mayor que `MAX_UPLOAD_BYTES` (50 MB) o parte JSON mayor que 1 MB |
| 400 | Sin `boundary`; primera parte no es JSON; JSON inválido; parte sin `filename`; **ningún archivo** |

### `GET .../folders/(folderId)/submissions/(submissionId)/files/(fileId)`

- **Scope**: `dropbox:folders:read` · **Quién**: STAFF, o el estudiante dueño de la entrega
- **Respuesta**: el archivo, con su `Content-Type` original y como descarga (`Content-Disposition`
  con el nombre). 404 si no existe o es de otro estudiante.
- [MOCK] Descargar no marca el archivo como leído (`isRead` sigue en `false`).

---

## 6. Retroalimentación

### `GET .../folders/(folderId)/feedback/(entityType)/(entityId)`

- **Scope**: `dropbox:folders:read` · **Quién**: STAFF; o el propio estudiante (solo si está publicada)
- `entityType`: `user` (`group` → 404, no soportado)
- **Respuesta**: `DropboxFeedbackOut` [DOC]

```json
{
  "Score": 80,
  "Feedback": { "Text": "Buen manejo de condicionales.", "Html": null },
  "RubricAssessments": [],
  "IsGraded": true,
  "GradedSymbol": null,
  "Files": [],
  "Links": []
}
```

| Error | Causa |
|---|---|
| 404 | No hay retroalimentación; o es borrador y quien pide es el estudiante; o la entidad no es estudiante del curso |
| 403 | Un estudiante pide la de otro |

### `POST .../folders/(folderId)/feedback/(entityType)/(entityId)`

- **Scope**: `dropbox:folders:write` · **Quién**: STAFF
- **Cuerpo**: `DropboxFeedback` [DOC]
- **Respuesta**: **200 sin cuerpo**

```json
{
  "Score": 80,
  "Feedback": { "Text": "Buen manejo de condicionales.", "Html": null },
  "IsGraded": true
}
```

| Campo | Regla |
|---|---|
| `Score` | Número ≥ 0 o `null` |
| `Feedback` | `RichText` o `RichTextInput` |
| `IsGraded` | `true` publica; `false` (por defecto) deja borrador |
| `RubricAssessments` | Debe ir vacío o ausente (no soportado) |
| `GradedSymbol` | Debe ser `null` o ausente (no soportado) |

**Cada POST reemplaza la retroalimentación completa**: si mandas `Score: null`, se borra el
puntaje anterior. Efecto en el libro de calificaciones: ver `07-ENTREGAS-RETRO-NOTAS.md`.

---

## 7. Calificaciones

Base: `/d2l/api/le/(version)/(orgUnitId)/grades/`

### Estructura `GradeObject` (numérico) [DOC]

```json
{
  "MaxPoints": 5.0,
  "CanExceedMaxPoints": false,
  "IsBonus": false,
  "ExcludeFromFinalGradeCalculation": false,
  "GradeSchemeId": null,
  "Id": 5001,
  "Name": "Taller 1: Condicionales",
  "ShortName": "T1",
  "GradeType": "Numeric",
  "CategoryId": null,
  "Description": { "Text": "Nota del taller 1", "Html": null },
  "GradeSchemeUrl": "/d2l/api/le/1.82/6650/grades/schemes/0",
  "Weight": 0,
  "AssociatedTool": { "ToolId": 2000, "ToolItemId": 701 },
  "IsHidden": false
}
```

[APROX] `GradeSchemeUrl` apunta a una ruta que el mock no implementa; `AssociatedTool` usa un
`ToolId` inventado y aparece cuando una carpeta está enlazada al ítem.

### Estructura `GradeValue` (numérico) [DOC]

```json
{
  "DisplayedGrade": "4 / 5",
  "GradeObjectIdentifier": "5001",
  "GradeObjectName": "Taller 1: Condicionales",
  "GradeObjectType": 1,
  "GradeObjectTypeName": "Numeric",
  "Comments": { "Text": "Buen manejo de condicionales.", "Html": null },
  "PrivateComments": { "Text": "", "Html": null },
  "LastModified": "2026-10-27T21:00:00.000Z",
  "LastModifiedBy": 3001,
  "ReleasedDate": "2026-10-27T21:00:00.000Z",
  "PointsNumerator": 4.0,
  "PointsDenominator": 5.0,
  "WeightedNumerator": null,
  "WeightedDenominator": null
}
```

[APROX] El formato de `DisplayedGrade` es inventado. `PrivateComments` va vacío para estudiantes.

### Rutas

| Ruta | Scope | Quién | Respuesta |
|---|---|---|---|
| `GET .../grades/` | `grades:gradeobjects:read` | MEMBERS (estudiantes no ven los ocultos) | Arreglo de `GradeObject` |
| `GET .../grades/(gradeObjectId)` | `grades:gradeobjects:read` | MEMBERS | `GradeObject` |
| `GET .../grades/(gradeObjectId)/values/` | `grades:gradevalues:read` | STAFF | `ObjectListPage` de `{ "User": User.User, "GradeValue": GradeValue \| null }`, uno por estudiante |
| `GET .../grades/(gradeObjectId)/values/(userId)` | `grades:gradevalues:read` | STAFF | `GradeValue` (404 si no tiene nota) |
| `PUT .../grades/(gradeObjectId)/values/(userId)` | `grades:gradevalues:write` | STAFF | 200 sin cuerpo [APROX] |
| `GET .../grades/(gradeObjectId)/values/myGradeValue` | `grades:own_grades:read` | STUDENT | `GradeValue` propio (404 si no hay) |
| `GET .../grades/values/myGradeValues/` | `grades:own_grades:read` | STUDENT | Arreglo de `GradeValue` propios |
| `GET .../grades/final/values/myGradeValue` | `grades:own_grades:read` | STUDENT | Nota final calculada (404 si no hay notas) |

**Query de `values/`**: `isGraded` (`true`: solo con nota; `false`: solo sin nota), `searchText`,
`pageSize` (1–200), `bookmark`. `values/` solo acepta ítems numéricos en el mock (todos lo son).

**Cuerpo del `PUT`** (`IncomingGradeValue` numérico [DOC]):

```json
{
  "GradeObjectType": 1,
  "PointsNumerator": 4.5,
  "Comments": { "Content": "Bien", "Type": "Text" },
  "PrivateComments": { "Content": "Revisar ciclo for", "Type": "Text" }
}
```

| Regla | Error |
|---|---|
| `GradeObjectType` debe ser 1 | 400 |
| `PointsNumerator` número ≥ 0 | 400 |
| `PointsNumerator` ≤ `MaxPoints`, salvo `CanExceedMaxPoints` | 400 |
| El usuario debe ser estudiante del curso | 404 |
| `Comments`/`PrivateComments` ausentes | Se conservan los anteriores |

[APROX] La nota queda **publicada** de inmediato (`ReleasedDate` = ahora).

**Nota final** (`final/values/myGradeValue`) [APROX: cálculo propio del mock]: suma de puntos
obtenidos ÷ suma de máximos, contando solo ítems **con nota publicada**, no ocultos, no bonus y no
excluidos. Devuelve `GradeObjectIdentifier: "0"`, `GradeObjectType: 7`,
`GradeObjectTypeName: "Final Calculated"`.

> El mock **no** permite crear ítems de calificación por API: los ítems vienen de los datos de
> demostración. Para tener más, hay que agregarlos en `app/seed.py` y reiniciar los datos.

---

## 8. Rutas del servidor de autorización

| Ruta | Para qué | Detalle |
|---|---|---|
| `GET /oauth2/auth` | Iniciar Authorization Code | `02-OAUTH-AUTHORIZATION-CODE.md` |
| `POST /oauth2/auth/login` | Formulario de login [MOCK] | — |
| `POST /oauth2/auth/consent` | Formulario de consentimiento [MOCK] | — |
| `POST /core/connect/token` | Canje de código, refresh y client credentials | `02` y `03` |
| `GET /d2l/logout` | Cierra la sesión del navegador en el mock | — |

## 9. Rutas solo del mock [MOCK]

| Ruta | Para qué |
|---|---|
| `GET /.mock/docs` | Documentación interactiva generada por FastAPI (Swagger UI) |
| `GET /.mock/openapi.json` | Esquema OpenAPI del mock |
| `GET /.mock/jwks` | Clave pública con la que el mock firma los tokens (para depurar) |
