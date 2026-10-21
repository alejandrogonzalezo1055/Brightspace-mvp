"""
Errores de la API con el formato de Brightspace.

[DOC] D2L no define un esquema JSON para los errores: el cuerpo es texto (a veces vacío).
Por ejemplo, un token inválido devuelve 403 con "Invalid Token" (no 401).
"""
from fastapi.responses import JSONResponse, PlainTextResponse


class D2LError(Exception):
    """Error de una ruta /d2l/api/...: se responde con texto plano."""

    def __init__(self, status: int, message: str = ""):
        super().__init__(message)
        self.status = status
        self.message = message

    def response(self) -> PlainTextResponse:
        return PlainTextResponse(self.message, status_code=self.status)


class OAuthError(Exception):
    """Error del endpoint de token: formato JSON del estándar OAuth 2.0 (RFC 6749 §5.2) [APROX]."""

    def __init__(self, error: str, description: str = "", status: int = 400):
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status = status

    def response(self) -> JSONResponse:
        body = {"error": self.error}
        if self.description:
            body["error_description"] = self.description
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
        if self.status == 401:
            headers["WWW-Authenticate"] = 'Basic realm="token"'
        return JSONResponse(body, status_code=self.status, headers=headers)


# Atajos para que las rutas se lean claro.
def invalid_token() -> D2LError:
    return D2LError(403, "Invalid Token")


def forbidden(message: str = "") -> D2LError:
    return D2LError(403, message)


def not_found(message: str = "") -> D2LError:
    return D2LError(404, message)


def bad_request(message: str) -> D2LError:
    return D2LError(400, message)
