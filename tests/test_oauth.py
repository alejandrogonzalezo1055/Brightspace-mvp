"""Flujo OAuth 2.0 completo: Authorization Code, refresh de un solo uso y Client Credentials con JWT."""
import base64
import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import apps
from tests.conftest import API, REDIRECT, browser_login_and_authorize, query_of

SCOPES = "users:own_profile:read enrollment:own_enrollment:read dropbox:folders:read"


@pytest.fixture
def registered(settings, app):
    client_id, secret = apps.register_authorization_code_app(
        settings, name="EduTrace", redirect_uri=REDIRECT, scopes=SCOPES, lifetime=3600, refresh=True, consent=True)
    return client_id, secret


def basic(client_id, secret):
    return {"Authorization": "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode()}


def get_code(client, client_id, scope=SCOPES, state="xyz", **kwargs):
    response = browser_login_and_authorize(client, {
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": scope, "state": state},
        **kwargs)
    assert response.status_code == 302, response.text
    return response.headers["location"]


def exchange(client, client_id, secret, code, redirect_uri=REDIRECT):
    return client.post("/core/connect/token", headers=basic(client_id, secret), data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})


def test_authorization_code_flow_end_to_end(client, registered):
    client_id, secret = registered
    location = get_code(client, client_id)
    assert location.startswith(REDIRECT + "?")
    params = query_of(location)
    assert params["state"] == "xyz" and params["code"]

    response = exchange(client, client_id, secret, params["code"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in", "scope", "refresh_token"}
    assert body["token_type"] == "Bearer" and body["expires_in"] == 3600 and body["scope"] == SCOPES

    who = client.get("/d2l/api/lp/1.49/users/whoami", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert who.status_code == 200
    assert who.json()["UniqueName"] == "estudiante1"
    assert who.json()["Identifier"] == "3101"


def test_client_secret_in_body_also_works(client, registered):
    client_id, secret = registered
    code = query_of(get_code(client, client_id))["code"]
    response = client.post("/core/connect/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "client_secret": secret})
    assert response.status_code == 200


def test_consent_is_remembered(client, registered):
    client_id, _ = registered
    get_code(client, client_id)
    # Segunda vez: la sesión del navegador sigue viva y el consentimiento ya se dio → redirige directo.
    response = client.get("/oauth2/auth", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": SCOPES})
    assert response.status_code == 302 and "code=" in response.headers["location"]


def test_redirect_uri_must_match_exactly(client, registered):
    client_id, _ = registered
    response = client.get("/oauth2/auth", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT + "/", "scope": SCOPES})
    assert response.status_code == 400 and "location" not in response.headers


def test_unknown_client_shows_error_page(client):
    response = client.get("/oauth2/auth", params={
        "response_type": "code", "client_id": "nope", "redirect_uri": REDIRECT, "scope": SCOPES})
    assert response.status_code == 400 and "location" not in response.headers


def test_unregistered_scope_redirects_with_error(client, registered):
    client_id, _ = registered
    response = client.get("/oauth2/auth", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "scope": "grades:gradevalues:write", "state": "s1"})
    assert response.status_code == 302
    params = query_of(response.headers["location"])
    assert params["error"] == "invalid_scope" and params["state"] == "s1"


def test_user_denies_consent(client, registered):
    client_id, _ = registered
    location = get_code(client, client_id, decision="deny")
    assert query_of(location)["error"] == "access_denied"


def test_wrong_password_and_csrf(client, registered):
    client_id, _ = registered
    response = browser_login_and_authorize(client, {
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": SCOPES},
        password="incorrecta")
    assert response.status_code == 401
    page = client.get("/oauth2/auth", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": SCOPES})
    forged = client.post("/oauth2/auth/login", data={"username": "estudiante1", "password": "Mock2026!",
                                                      "request": "", "csrf": "falso"})
    assert page.status_code == 200 and forged.status_code == 400


def test_code_is_single_use_and_bound_to_redirect_uri(client, registered):
    client_id, secret = registered
    code = query_of(get_code(client, client_id))["code"]
    assert exchange(client, client_id, secret, code, redirect_uri="http://otra").json()["error"] == "invalid_grant"
    assert exchange(client, client_id, secret, code).status_code == 200
    reused = exchange(client, client_id, secret, code)
    assert reused.status_code == 400 and reused.json()["error"] == "invalid_grant"


def test_wrong_secret_is_invalid_client(client, registered):
    client_id, _ = registered
    code = query_of(get_code(client, client_id))["code"]
    response = exchange(client, client_id, "secreto-malo", code)
    assert response.status_code == 401 and response.json()["error"] == "invalid_client"


def test_refresh_tokens_are_single_use(client, registered):
    client_id, secret = registered
    first = exchange(client, client_id, secret, query_of(get_code(client, client_id))["code"]).json()

    def refresh(token):
        return client.post("/core/connect/token", headers=basic(client_id, secret),
                           data={"grant_type": "refresh_token", "refresh_token": token})

    second = refresh(first["refresh_token"])
    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]
    reused = refresh(first["refresh_token"])
    assert reused.status_code == 400 and reused.json()["error"] == "invalid_grant"
    assert refresh(second.json()["refresh_token"]).status_code == 200


def test_token_endpoint_requires_form_encoding(client, registered):
    response = client.post("/core/connect/token", json={"grant_type": "authorization_code"})
    assert response.status_code == 400 and response.json()["error"] == "invalid_request"


# ───────────────────────── Client Credentials ─────────────────────────

@pytest.fixture
def s2s(settings, app, tmp_path):
    """App servidor a servidor con su par de claves y su JWKS publicado en un archivo."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "edutrace-key-1", "alg": "RS256", "use": "sig"})
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps({"keys": [jwk]}))
    client_id = apps.register_client_credentials_app(
        settings, name="EduTrace sync", jwks_url=f"file://{jwks_path}",
        scopes="enrollment:orgunit:read dropbox:folders:read users:own_profile:read", service_username="svc_edutrace")
    return client_id, private_key


def assertion(client_id, private_key, *, aud=f"{API}/core/connect/token", lifetime=60, jti=None, kid="edutrace-key-1"):
    now = int(time.time())
    claims = {"iss": client_id, "sub": client_id, "aud": aud, "iat": now, "exp": now + lifetime,
              "jti": jti or str(uuid.uuid4())}
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def cc_request(client, signed, scope="enrollment:orgunit:read dropbox:folders:read"):
    return client.post("/core/connect/token", data={
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": signed, "scope": scope})


def test_client_credentials_flow(client, s2s):
    client_id, key = s2s
    response = cc_request(client, assertion(client_id, key))
    assert response.status_code == 200, response.text
    body = response.json()
    assert "refresh_token" not in body
    folders = client.get("/d2l/api/le/1.82/6650/dropbox/folders/",
                         headers={"Authorization": f"Bearer {body['access_token']}"})
    assert folders.status_code == 200
    assert {f["Id"] for f in folders.json()} >= {701, 702, 703}  # el usuario de servicio ve también las ocultas


def test_client_credentials_rejections(client, s2s):
    client_id, key = s2s
    reused = assertion(client_id, key, jti="fijo")
    assert cc_request(client, reused).status_code == 200
    assert cc_request(client, reused).json()["error"] == "invalid_client"  # jti repetido
    assert cc_request(client, assertion(client_id, key, aud="https://otro/token")).status_code == 401
    assert cc_request(client, assertion(client_id, key, lifetime=600)).status_code == 401
    assert cc_request(client, assertion(client_id, key, kid="no-existe")).status_code == 401
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert cc_request(client, assertion(client_id, other_key)).status_code == 401  # firma con otra clave
    scope_err = cc_request(client, assertion(client_id, key), scope="grades:gradevalues:write")
    assert scope_err.json()["error"] == "invalid_scope"
