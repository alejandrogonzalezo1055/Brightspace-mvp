"""
Rutas HTTP del servidor de autorización:

  GET  /oauth2/auth            inicio del flujo Authorization Code [DOC]
  POST /oauth2/auth/login      formulario de login del mock
  POST /oauth2/auth/consent    formulario de consentimiento del mock
  POST /core/connect/token     emisión y canje de tokens [DOC]
  GET  /d2l/logout             cierra la sesión del navegador en el mock
  GET  /.mock/jwks             clave pública del mock (SOLO existe en el mock)
"""
import hmac
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.db import transaction
from app.errors import OAuthError
from app.oauth import pages
from app.oauth import service

router = APIRouter()

SESSION_COOKIE = "d2lSessionVal"     # [APROX] nombre de la cookie de sesión del navegador
LOGIN_CSRF_COOKIE = "mock_login_csrf"


def _settings(request: Request):
    return request.app.state.settings


def _html(content: str, status: int = 200) -> HTMLResponse:
    # Las páginas de login no se deben cachear ni mostrar dentro de iframes ajenos.
    return HTMLResponse(content, status_code=status, headers={
        "Cache-Control": "no-store", "X-Frame-Options": "DENY"})


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=302)


def _login_form(request: Request, query: str, error: str = "", status: int = 200) -> HTMLResponse:
    csrf = secrets.token_urlsafe(24)
    response = _html(pages.login_page(request_query=query, csrf=csrf, error=error), status)
    response.set_cookie(LOGIN_CSRF_COOKIE, csrf, httponly=True, samesite="lax",
                        secure=_settings(request).cookie_secure, path="/oauth2/auth")
    return response


def _continue_after_login(conn, request: Request, req: service.AuthorizationRequest, user) -> HTMLResponse | RedirectResponse:
    """Con el usuario ya identificado: pedir consentimiento si hace falta, o emitir el código."""
    if service.needs_consent(conn, user["id"], req.client):
        return _html(pages.consent_page(
            app_name=req.client["name"], user_name=f"{user['first_name']} {user['last_name']}",
            scopes=req.scope.split(), request_query=req.query, csrf=user["csrf_token"]))
    return _redirect(service.issue_code_redirect(conn, _settings(request), req, user["id"]))


@router.get("/oauth2/auth")
def authorize(request: Request):
    query = request.url.query
    with transaction(_settings(request).db_path) as conn:
        try:
            req = service.validate_authorization_request(conn, query)
        except service.ShowErrorPage as exc:
            return _html(pages.error_page(str(exc)), 400)
        except service.RedirectWithError as exc:
            return _redirect(exc.url)

        user = service.get_login_session(conn, request.cookies.get(SESSION_COOKIE))
        if user is None:
            return _login_form(request, req.query)
        return _continue_after_login(conn, request, req, user)


@router.post("/oauth2/auth/login")
async def login(request: Request):
    form = await request.form()
    query = str(form.get("request", ""))
    settings = _settings(request)

    # Protección CSRF de doble envío: el valor del formulario debe coincidir con el de la cookie.
    cookie_csrf = request.cookies.get(LOGIN_CSRF_COOKIE, "")
    if not cookie_csrf or not hmac.compare_digest(cookie_csrf, str(form.get("csrf", ""))):
        return _login_form(request, query, "La sesión del formulario expiró. Intenta de nuevo.", 400)

    with transaction(settings.db_path) as conn:
        try:
            req = service.validate_authorization_request(conn, query)
        except service.ShowErrorPage as exc:
            return _html(pages.error_page(str(exc)), 400)
        except service.RedirectWithError as exc:
            return _redirect(exc.url)

        user = service.authenticate_user(conn, str(form.get("username", "")), str(form.get("password", "")))
        if user is None:
            return _login_form(request, query, "Usuario o contraseña incorrectos.", 401)

        session_id = service.create_login_session(conn, settings, user["id"])
        session_user = service.get_login_session(conn, session_id)
        response = _continue_after_login(conn, request, req, session_user)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, max_age=settings.login_session_ttl_s)
    response.delete_cookie(LOGIN_CSRF_COOKIE, path="/oauth2/auth")
    return response


@router.post("/oauth2/auth/consent")
async def consent(request: Request):
    form = await request.form()
    query = str(form.get("request", ""))
    with transaction(_settings(request).db_path) as conn:
        user = service.get_login_session(conn, request.cookies.get(SESSION_COOKIE))
        if user is None:
            return _login_form(request, query, "Tu sesión expiró. Inicia sesión de nuevo.", 401)
        if not hmac.compare_digest(user["csrf_token"], str(form.get("csrf", ""))):
            return _html(pages.error_page("Solicitud de consentimiento inválida (CSRF)."), 400)
        try:
            req = service.validate_authorization_request(conn, query)
        except service.ShowErrorPage as exc:
            return _html(pages.error_page(str(exc)), 400)
        except service.RedirectWithError as exc:
            return _redirect(exc.url)

        if form.get("decision") != "allow":
            return _redirect(service.denied_redirect(req))
        service.remember_consent(conn, user["id"], req.client["client_id"])
        return _redirect(service.issue_code_redirect(conn, _settings(request), req, user["id"]))


@router.post("/core/connect/token")
async def token(request: Request):
    settings = _settings(request)
    try:
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/x-www-form-urlencoded":
            raise OAuthError("invalid_request", "Content-Type debe ser application/x-www-form-urlencoded")
        form = {k: str(v) for k, v in (await request.form()).items()}
        grant_type = form.get("grant_type", "")
        with transaction(settings.db_path) as conn:
            if grant_type == "authorization_code":
                body = service.exchange_code(conn, settings, request.app.state.signing_key,
                                             request.headers.get("authorization"), form)
            elif grant_type == "refresh_token":
                body = service.exchange_refresh_token(conn, settings, request.app.state.signing_key,
                                                      request.headers.get("authorization"), form)
            elif grant_type == "client_credentials":
                body = service.client_credentials(conn, settings, request.app.state.signing_key, form)
            else:
                raise OAuthError("unsupported_grant_type", f"grant_type no soportado: {grant_type!r}")
    except OAuthError as exc:
        return exc.response()
    return JSONResponse(body, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@router.get("/d2l/logout")
def logout(request: Request):
    with transaction(_settings(request).db_path) as conn:
        service.delete_login_session(conn, request.cookies.get(SESSION_COOKIE))
    response = _html("<p>Sesión cerrada.</p>")
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/.mock/jwks")
def mock_jwks(request: Request):
    return {"keys": [request.app.state.signing_key.public_jwk]}
