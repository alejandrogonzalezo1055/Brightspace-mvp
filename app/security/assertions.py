"""
Verificación de la aserción JWT del flujo Client Credentials (servidor a servidor) [DOC].

Lo que el cliente debe mandar en client_assertion:
  encabezado: alg (RS256/384/512, ES256/384/512) y kid (la clave en su JWKS)
  claims:     aud = URL exacta del endpoint de token
              iss = sub = client_id
              iat, exp (vida recomendada ≤ 60 s; el mock rechaza más de 5 min)
              jti único y de un solo uso

Brightspace busca la clave pública en la URL JWKS registrada para la app.
"""
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import jwt

ALLOWED_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
MAX_LIFETIME_S = 300
CLOCK_SKEW_S = 30


class InvalidAssertion(Exception):
    """La aserción no es válida. El mensaje se devuelve como error_description."""


def _load_jwks(jwks_url: str, allow_insecure: bool) -> dict:
    parsed = urlparse(jwks_url)
    if parsed.scheme == "https":
        pass
    elif parsed.scheme in {"http", "file"} and allow_insecure:
        pass
    else:
        raise InvalidAssertion("la URL JWKS registrada debe ser HTTPS")
    try:
        if parsed.scheme == "file":
            return json.loads(Path(parsed.path).read_text())
        response = httpx.get(jwks_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except (OSError, ValueError, httpx.HTTPError) as exc:
        raise InvalidAssertion(f"no se pudo leer el JWKS del cliente: {exc}") from exc


def verify_client_assertion(conn: sqlite3.Connection, *, assertion: str, client: sqlite3.Row,
                            token_endpoint: str, allow_insecure_jwks: bool) -> None:
    try:
        header = jwt.get_unverified_header(assertion)
    except jwt.PyJWTError as exc:
        raise InvalidAssertion(f"client_assertion no es un JWT: {exc}") from exc

    alg, kid = header.get("alg"), header.get("kid")
    if alg not in ALLOWED_ALGS:
        raise InvalidAssertion(f"alg no permitido: {alg!r}")
    if not kid:
        raise InvalidAssertion("falta 'kid' en el encabezado del JWT")

    jwks = _load_jwks(client["jwks_url"], allow_insecure_jwks)
    jwk = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if jwk is None:
        raise InvalidAssertion(f"el JWKS del cliente no tiene la clave kid={kid!r}")
    try:
        public_key = jwt.PyJWK(jwk, algorithm=alg).key
        claims = jwt.decode(
            assertion,
            public_key,
            algorithms=[alg],
            audience=token_endpoint,
            issuer=client["client_id"],
            leeway=CLOCK_SKEW_S,
            options={"require": ["aud", "iss", "sub", "iat", "exp", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAssertion(f"aserción inválida: {exc}") from exc

    if claims["sub"] != client["client_id"]:
        raise InvalidAssertion("'sub' debe ser igual al client_id")
    if claims["exp"] - claims["iat"] > MAX_LIFETIME_S:
        raise InvalidAssertion("la aserción vive más de 5 minutos")

    # jti de un solo uso: si ya se vio, es un intento de repetir la aserción.
    now = time.time()
    conn.execute("DELETE FROM oauth_used_jti WHERE expires_at < ?", (now,))
    try:
        conn.execute(
            "INSERT INTO oauth_used_jti (client_id, jti, expires_at) VALUES (?, ?, ?)",
            (client["client_id"], str(claims["jti"]), claims["exp"] + CLOCK_SKEW_S),
        )
    except sqlite3.IntegrityError as exc:
        raise InvalidAssertion("el 'jti' ya se usó: cada aserción es de un solo uso") from exc
