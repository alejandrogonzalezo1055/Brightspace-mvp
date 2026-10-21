import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security.tokens import issue_access_token  # noqa: E402

API = "http://testserver"
REDIRECT = "http://localhost:9000/callback"
ALL_SCOPES = ("users:profile:read users:own_profile:read users:userdata:read enrollment:own_enrollment:read "
              "enrollment:orgunit:read dropbox:folders:read,write grades:gradeobjects:read grades:gradevalues:* "
              "grades:own_grades:read")


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings()
    s.data_dir = tmp_path / "data"
    s.auth_base_url = API
    s.api_base_url = API
    s.rate_limit_capacity = 10_000
    return s


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app, base_url=API, follow_redirects=False)


@pytest.fixture
def token_for(app):
    """Atajo para pruebas de la API: emite un token firmado por el mock sin pasar por el navegador."""

    def make(user_id: int, scope: str = ALL_SCOPES, lifetime: int = 3600, client_id: str = "test-app") -> dict:
        token = issue_access_token(app.state.signing_key, user_id=user_id, client_id=client_id, scope=scope,
                                   lifetime_s=lifetime, tenant_id=app.state.settings.tenant_id)
        return {"Authorization": f"Bearer {token}"}

    return make


def hidden_field(html: str, name: str) -> str:
    match = re.search(rf'name="{name}" value="([^"]*)"', html)
    assert match, f"no se encontró el campo {name}"
    import html as html_lib
    return html_lib.unescape(match.group(1))


def query_of(location: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def browser_login_and_authorize(client: TestClient, authorize_params: dict, username="estudiante1",
                                password="Mock2026!", decision="allow"):
    """Simula al usuario en el navegador: abre /oauth2/auth, inicia sesión y (si se pide) autoriza."""
    page = client.get("/oauth2/auth", params=authorize_params)
    assert page.status_code == 200, page.text
    response = client.post("/oauth2/auth/login", data={
        "username": username, "password": password,
        "request": hidden_field(page.text, "request"), "csrf": hidden_field(page.text, "csrf")})
    if response.status_code == 200 and "Autorizar" in response.text:
        response = client.post("/oauth2/auth/consent", data={
            "request": hidden_field(response.text, "request"), "csrf": hidden_field(response.text, "csrf"),
            "decision": decision})
    return response
