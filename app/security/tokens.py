"""
Access tokens del mock: JWT firmados con RS256.

Los claims imitan un token real de Brightspace (iss, aud, sub, tenantid, azp, scope, jti, nbf,
exp). [APROX] El cliente de EduTrace debe tratar el token como un string opaco: no debe leerlo
ni depender de lo que tenga adentro, porque D2L no garantiza su formato.
"""
import secrets
import time

import jwt

from app.security.keys import SigningKey

ISSUER = "https://api.brightspace.com/auth"
AUDIENCE = "https://api.brightspace.com/auth/token"


def issue_access_token(key: SigningKey, *, user_id: int, client_id: str, scope: str,
                       lifetime_s: int, tenant_id: str) -> str:
    now = int(time.time())
    claims = {
        "nbf": now,
        "exp": now + lifetime_s,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "tenantid": tenant_id,
        "azp": client_id,
        "scope": scope,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(claims, key.private_key, algorithm="RS256", headers={"kid": key.kid, "typ": "JWT"})


def verify_access_token(key: SigningKey, token: str) -> dict | None:
    """Devuelve los claims si el token es válido y está vigente; None en cualquier otro caso."""
    try:
        return jwt.decode(
            token,
            key.private_key.public_key(),
            algorithms=["RS256"],  # lista fija: nunca aceptar el 'alg' que diga el token
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "nbf", "sub", "azp", "scope"]},
        )
    except jwt.PyJWTError:
        return None
