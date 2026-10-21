"""
Lógica del servidor de autorización: validar solicitudes, emitir códigos y tokens.

Las rutas HTTP (routes.py) solo leen la petición y arman la respuesta; todo lo que decide algo
está aquí.
"""
import base64
import secrets
import sqlite3
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlencode

import jwt

from app.config import Settings
from app.errors import OAuthError
from app.security import scopes as scope_rules
from app.security.assertions import InvalidAssertion, verify_client_assertion
from app.security.keys import SigningKey
from app.security.passwords import check_password, sha256_hex
from app.security.tokens import issue_access_token


# ───────────────────────── /oauth2/auth ─────────────────────────

class ShowErrorPage(Exception):
    """Error que NO se redirige (client_id o redirect_uri inválidos): se muestra una página."""


class RedirectWithError(Exception):
    """Error que SÍ se redirige a la app: redirect_uri?error=...&state=..."""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


@dataclass
class AuthorizationRequest:
    client: sqlite3.Row
    redirect_uri: str
    scope: str
    state: str | None
    query: str  # la query original, para reenviarla en los formularios de login y consentimiento


def _with_params(base: str, params: dict) -> str:
    params = {k: v for k, v in params.items() if v is not None}
    return base + ("&" if "?" in base else "?") + urlencode(params)


def validate_authorization_request(conn: sqlite3.Connection, query: str) -> AuthorizationRequest:
    params = dict(parse_qsl(query, keep_blank_values=True))
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state")

    client = conn.execute(
        "SELECT * FROM oauth_clients WHERE client_id = ? AND grant_type = 'authorization_code'",
        (client_id,),
    ).fetchone()
    if client is None:
        raise ShowErrorPage("client_id desconocido o la app no es de tipo Authorization Code.")
    # La redirect_uri debe ser EXACTAMENTE la registrada: ni una barra de más.
    if redirect_uri != client["redirect_uri"]:
        raise ShowErrorPage("redirect_uri no coincide exactamente con la registrada para la app.")

    def fail(error: str, description: str):
        raise RedirectWithError(_with_params(redirect_uri, {
            "error": error, "error_description": description, "state": state}))

    if params.get("response_type") != "code":
        fail("unsupported_response_type", "solo se admite response_type=code")
    requested_scope = params.get("scope", "").strip()
    if not requested_scope:
        fail("invalid_scope", "falta el parámetro scope")
    try:
        if not scope_rules.is_subset(requested_scope, client["scopes"]):
            fail("invalid_scope", "se pidieron scopes que la app no tiene registrados")
    except scope_rules.ScopeSyntaxError as exc:
        fail("invalid_scope", str(exc))

    return AuthorizationRequest(client=client, redirect_uri=redirect_uri, scope=requested_scope,
                                state=state, query=query)


def needs_consent(conn: sqlite3.Connection, user_id: int, client: sqlite3.Row) -> bool:
    if not client["prompt_consent"]:
        return False
    row = conn.execute("SELECT 1 FROM oauth_consents WHERE user_id = ? AND client_id = ?",
                       (user_id, client["client_id"])).fetchone()
    return row is None


def remember_consent(conn: sqlite3.Connection, user_id: int, client_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO oauth_consents (user_id, client_id) VALUES (?, ?)", (user_id, client_id))


def issue_code_redirect(conn: sqlite3.Connection, settings: Settings, req: AuthorizationRequest, user_id: int) -> str:
    code = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri, scope, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (sha256_hex(code), req.client["client_id"], user_id, req.redirect_uri, req.scope,
         time.time() + settings.auth_code_ttl_s),
    )
    return _with_params(req.redirect_uri, {"code": code, "state": req.state})


def denied_redirect(req: AuthorizationRequest) -> str:
    return _with_params(req.redirect_uri, {
        "error": "access_denied", "error_description": "el usuario no autorizó la aplicación", "state": req.state})


# ───────────────────────── sesiones del navegador (login) ─────────────────────────

def authenticate_user(conn: sqlite3.Connection, username: str, password: str) -> sqlite3.Row | None:
    user = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username.strip(),)).fetchone()
    if user is None or not check_password(password, user["password_hash"]):
        return None
    return user


def create_login_session(conn: sqlite3.Connection, settings: Settings, user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM login_sessions WHERE expires_at < ?", (time.time(),))
    conn.execute(
        "INSERT INTO login_sessions (session_hash, user_id, csrf_token, expires_at) VALUES (?, ?, ?, ?)",
        (sha256_hex(session_id), user_id, secrets.token_urlsafe(24), time.time() + settings.login_session_ttl_s),
    )
    return session_id


def get_login_session(conn: sqlite3.Connection, session_id: str | None) -> sqlite3.Row | None:
    if not session_id:
        return None
    return conn.execute(
        """SELECT s.csrf_token, u.* FROM login_sessions s JOIN users u ON u.id = s.user_id
           WHERE s.session_hash = ? AND s.expires_at > ? AND u.is_active = 1""",
        (sha256_hex(session_id), time.time()),
    ).fetchone()


def delete_login_session(conn: sqlite3.Connection, session_id: str | None) -> None:
    if session_id:
        conn.execute("DELETE FROM login_sessions WHERE session_hash = ?", (sha256_hex(session_id),))


# ───────────────────────── /core/connect/token ─────────────────────────

def _client_from_basic_or_body(conn: sqlite3.Connection, authorization: str | None, form: dict) -> sqlite3.Row:
    """Autentica una app Authorization Code con HTTP Basic o con client_id/client_secret en el cuerpo."""
    basic = None
    if authorization and authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization[6:].strip()).decode()
            basic = tuple(unquote(part) for part in decoded.split(":", 1))
        except (ValueError, UnicodeDecodeError):
            raise OAuthError("invalid_client", "encabezado Basic mal formado", 401)
        if len(basic) != 2:
            raise OAuthError("invalid_client", "encabezado Basic mal formado", 401)

    if basic and form.get("client_secret"):
        raise OAuthError("invalid_request", "usa HTTP Basic o client_secret en el cuerpo, no ambos")
    client_id, secret = basic if basic else (form.get("client_id", ""), form.get("client_secret", ""))
    if basic and form.get("client_id") and form["client_id"] != client_id:
        raise OAuthError("invalid_request", "client_id del cuerpo no coincide con el de HTTP Basic")

    client = conn.execute(
        "SELECT * FROM oauth_clients WHERE client_id = ? AND grant_type = 'authorization_code'", (client_id,)
    ).fetchone()
    if client is None or not check_password(secret, client["secret_hash"]):
        raise OAuthError("invalid_client", "credenciales de cliente inválidas", 401)
    return client


def _token_response(conn: sqlite3.Connection, settings: Settings, key: SigningKey, *, client: sqlite3.Row,
                    user_id: int, scope: str, with_refresh: bool) -> dict:
    lifetime = int(client["token_lifetime"])
    body = {
        "access_token": issue_access_token(key, user_id=user_id, client_id=client["client_id"], scope=scope,
                                           lifetime_s=lifetime, tenant_id=settings.tenant_id),
        "token_type": "Bearer",
        "expires_in": lifetime,
        "scope": scope,
    }
    if with_refresh:
        refresh = secrets.token_urlsafe(48)
        conn.execute(
            "INSERT INTO oauth_refresh_tokens (token_hash, client_id, user_id, scope, expires_at) VALUES (?, ?, ?, ?, ?)",
            (sha256_hex(refresh), client["client_id"], user_id, scope, time.time() + settings.refresh_token_ttl_s),
        )
        body["refresh_token"] = refresh
    return body


def exchange_code(conn, settings, key, authorization, form) -> dict:
    client = _client_from_basic_or_body(conn, authorization, form)
    code = form.get("code", "")
    row = conn.execute("SELECT * FROM oauth_codes WHERE code_hash = ?", (sha256_hex(code),)).fetchone()
    if row is None or row["client_id"] != client["client_id"]:
        raise OAuthError("invalid_grant", "código de autorización inválido")
    if row["used"]:
        raise OAuthError("invalid_grant", "el código de autorización ya se usó")
    if row["expires_at"] < time.time():
        raise OAuthError("invalid_grant", "el código de autorización venció")
    if form.get("redirect_uri") != row["redirect_uri"]:
        raise OAuthError("invalid_grant", "redirect_uri distinta a la usada al pedir el código")
    conn.execute("UPDATE oauth_codes SET used = 1 WHERE code_hash = ?", (row["code_hash"],))
    return _token_response(conn, settings, key, client=client, user_id=row["user_id"], scope=row["scope"],
                           with_refresh=bool(client["refresh_enabled"]))


def exchange_refresh_token(conn, settings, key, authorization, form) -> dict:
    client = _client_from_basic_or_body(conn, authorization, form)
    if not client["refresh_enabled"]:
        raise OAuthError("unauthorized_client", "la app no tiene habilitados los refresh tokens")
    token = form.get("refresh_token", "")
    row = conn.execute("SELECT * FROM oauth_refresh_tokens WHERE token_hash = ?", (sha256_hex(token),)).fetchone()
    if row is None or row["client_id"] != client["client_id"]:
        raise OAuthError("invalid_grant", "refresh token inválido")
    if row["used"]:
        raise OAuthError("invalid_grant", "el refresh token ya se usó: son de un solo uso")
    if row["expires_at"] < time.time():
        raise OAuthError("invalid_grant", "el refresh token venció")

    scope = row["scope"]
    if form.get("scope"):
        try:
            if not scope_rules.is_subset(form["scope"], row["scope"]):
                raise OAuthError("invalid_scope", "el scope pedido es más amplio que el original")
        except scope_rules.ScopeSyntaxError as exc:
            raise OAuthError("invalid_scope", str(exc))
        scope = form["scope"]

    conn.execute("UPDATE oauth_refresh_tokens SET used = 1 WHERE token_hash = ?", (row["token_hash"],))
    return _token_response(conn, settings, key, client=client, user_id=row["user_id"], scope=scope, with_refresh=True)


JWT_BEARER = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def client_credentials(conn, settings, key, form) -> dict:
    if form.get("client_assertion_type") != JWT_BEARER:
        raise OAuthError("invalid_client", f"client_assertion_type debe ser {JWT_BEARER}", 401)
    assertion = form.get("client_assertion", "")
    try:
        # Se lee el 'iss' SIN verificar solo para saber qué app es; la firma se verifica después.
        client_id = jwt.decode(assertion, options={"verify_signature": False}).get("iss", "")
    except Exception:
        raise OAuthError("invalid_client", "client_assertion no es un JWT", 401)

    client = conn.execute(
        "SELECT * FROM oauth_clients WHERE client_id = ? AND grant_type = 'client_credentials'", (client_id,)
    ).fetchone()
    if client is None:
        raise OAuthError("invalid_client", "app desconocida o no es de tipo Client Credentials", 401)
    try:
        verify_client_assertion(conn, assertion=assertion, client=client, token_endpoint=settings.token_endpoint,
                                allow_insecure_jwks=settings.allow_insecure_jwks)
    except InvalidAssertion as exc:
        raise OAuthError("invalid_client", str(exc), 401)

    scope = form.get("scope", "").strip()
    if not scope:
        raise OAuthError("invalid_scope", "falta el parámetro scope")
    try:
        if not scope_rules.is_subset(scope, client["scopes"]):
            raise OAuthError("invalid_scope", "se pidieron scopes que la app no tiene registrados")
    except scope_rules.ScopeSyntaxError as exc:
        raise OAuthError("invalid_scope", str(exc))

    return _token_response(conn, settings, key, client=client, user_id=client["service_user_id"], scope=scope,
                           with_refresh=False)
