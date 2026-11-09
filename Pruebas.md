## Prueba manual inicial con Postman:

Respuesta al registro de la app de Postman:

```
App registrada (Authorization Code).
  client_id:     d442ef97-75a3-4fb8-b3a5-d8c3dd5e53d4
  client_secret: UoAAIcGG47XhgbKdToBYfVzaefksOKelhVso3oOX-JI
  Guarda el secreto ahora: no se puede volver a mostrar.
```

URI para la peticion al navegador:
http://100.74.69.65:8800/oauth2/auth?response_type=code&client_id=d442ef97-75a3-4fb8-b3a5-d8c3dd5e53d4&redirect_uri=http://localhost:9000/callback&scope=users:own_profile:read%20enrollment:own_enrollment:read%20dropbox:folders:read&state=prueba123


Respuesta a mandar la peticion en el navegador:

```
Codigo devuelto al iniciar secion:
    tp7of3p8Z5jexXVikZiyC33RisDQQBKtYXVVYaraL70
    
    Para obtenerlo es necesario mandar el client id en la peticion.
```

Para hacer alguna peticion el usuario debe autorizar, por eso se inicia sesion.

Inicialmente, la peticion de autorizacion se hace con grant_type=authorization_code y el codigo obtenido al iniciar sesion en el navegador.

Al mandar la peticion de autorizacion devuelve:

```json
{
  "acces_token": "...",
  "token_type": "Bearer",
  "expires_in": "3600",
  "scope": "el mismo que la peticion en el navegador",
  "refresh_token": "..."
}
```

Registro de la app de EduTrace:

```
App registrada (Authorization Code).
  client_id:     4274c8db-31b5-43f6-bdd1-d076e9327553
  client_secret: MF0UAaXy0y9VYcwiVWqtLR-hrWA7JlLkbEeKIMcr7vE
  Guarda el secreto ahora: no se puede volver a mostrar.
```

users:own_profile:read enrollment:own_enrollment:read enrollment:orgunit:read dropbox:folders:read,write grades:gradeobjects:read grades:gradevalues:read grades:own_grades:read
users:own_profile:read%20enrollment:own_enrollment:read%20enrollment:orgunit:read%20dropbox:folders:read,write%20grades:gradeobjects:read%20grades:gradevalues:read%20grades:own_grades:read

## Prueba 2

Respuesta al registro de la app Pruebas1:

```
App registrada (Authorization Code).
  client_id:     ff4f1c89-28fc-45f2-8ac0-0252042f9eb4
  client_secret: 59tZ6trK_rdrqHhhJbunfDjnt_fTQOaFmL8JPFI8Qco
  Guarda el secreto ahora: no se puede volver a mostrar.
```

URI para la peticion al navegador:
http://100.74.69.65:8800/oauth2/auth?response_type=code&client_id=ff4f1c89-28fc-45f2-8ac0-0252042f9eb4&redirect_uri=http://localhost:9000/auth/callback&scope=users:own_profile:read%20enrollment:own_enrollment:read%20enrollment:orgunit:read%20dropbox:folders:read,write%20grades:gradeobjects:read%20grades:gradevalues:read%20grades:own_grades:read&state=prueba123
