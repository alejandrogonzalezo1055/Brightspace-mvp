"""
Registro de aplicaciones OAuth 2.0: el equivalente a Admin Tools > Manage Extensibility > OAuth 2.0
> Register an app [DOC]. En el mock se hace por línea de comandos (admin.py).
"""
import secrets
import uuid

from app.config import Settings
from app.db import now_str, transaction
from app.security import scopes as scope_rules
from app.security.passwords import hash_password

MIN_LIFETIME, MAX_LIFETIME = 1800, 72000  # [DOC] entre 30 minutos y 20 horas


class RegistrationError(ValueError):
    pass


def _check_common(scopes: str, lifetime: int) -> None:
    if not scopes.strip():
        raise RegistrationError("hay que registrar al menos un scope")
    try:
        scope_rules.parse(scopes)
    except scope_rules.ScopeSyntaxError as exc:
        raise RegistrationError(str(exc)) from exc
    if not MIN_LIFETIME <= lifetime <= MAX_LIFETIME:
        raise RegistrationError(f"la vida del token debe estar entre {MIN_LIFETIME} y {MAX_LIFETIME} segundos")


def register_authorization_code_app(settings: Settings, *, name: str, redirect_uri: str, scopes: str,
                                    lifetime: int = 3600, refresh: bool = True, consent: bool = True) -> tuple[str, str]:
    """Devuelve (client_id, client_secret). El secreto solo se muestra esta vez: en la base queda su hash."""
    _check_common(scopes, lifetime)
    if not redirect_uri.startswith(("https://", "http://")):
        raise RegistrationError("redirect_uri debe ser una URL http(s) absoluta")
    client_id = str(uuid.uuid4())
    client_secret = secrets.token_urlsafe(32)
    with transaction(settings.db_path) as conn:
        conn.execute(
            """INSERT INTO oauth_clients (client_id, name, grant_type, secret_hash, redirect_uri, scopes,
                                          token_lifetime, refresh_enabled, prompt_consent, created_at)
               VALUES (?, ?, 'authorization_code', ?, ?, ?, ?, ?, ?, ?)""",
            (client_id, name, hash_password(client_secret), redirect_uri, " ".join(scopes.split()), lifetime,
             int(refresh), int(consent), now_str()))
    return client_id, client_secret


def register_client_credentials_app(settings: Settings, *, name: str, jwks_url: str, scopes: str,
                                    service_username: str, lifetime: int = 3600) -> str:
    """Devuelve el client_id. No hay secreto: la app se autentica firmando un JWT con su clave privada."""
    _check_common(scopes, lifetime)
    if not jwks_url.startswith("https://") and not settings.allow_insecure_jwks:
        raise RegistrationError("la URL JWKS debe ser HTTPS")
    with transaction(settings.db_path) as conn:
        user = conn.execute(
            "SELECT u.id FROM users u JOIN roles r ON r.id = u.org_role_id WHERE u.username = ? AND r.kind = 'service'",
            (service_username,)).fetchone()
        if user is None:
            raise RegistrationError(f"no existe el usuario de servicio {service_username!r}")
        client_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO oauth_clients (client_id, name, grant_type, jwks_url, service_user_id, scopes,
                                          token_lifetime, refresh_enabled, prompt_consent, created_at)
               VALUES (?, ?, 'client_credentials', ?, ?, ?, ?, 0, 0, ?)""",
            (client_id, name, jwks_url, user["id"], " ".join(scopes.split()), lifetime, now_str()))
    return client_id


def list_apps(settings: Settings) -> list[dict]:
    with transaction(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM oauth_clients ORDER BY created_at").fetchall()
    return [{k: row[k] for k in row.keys() if k != "secret_hash"} for row in rows]


def delete_app(settings: Settings, client_id: str) -> bool:
    with transaction(settings.db_path) as conn:
        return conn.execute("DELETE FROM oauth_clients WHERE client_id = ?", (client_id,)).rowcount > 0
