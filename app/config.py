"""
Configuración del mock. Todo se lee de variables de entorno (con valores por defecto para
desarrollo), igual que se configuraría el backend de EduTrace.

[APROX] marca valores que D2L no publica: el mock los inventa y los deja configurables.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


def _versions(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


@dataclass
class Settings:
    # Carpeta donde viven la base SQLite, los archivos entregados y la clave de firma.
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", PROJECT_DIR / "data")))

    # En Brightspace real son dos hosts distintos: auth.brightspace.com y <institución>.brightspace.com.
    # El mock sirve ambos desde el mismo proceso, pero se configuran por separado para que el
    # cliente de EduTrace también los tenga separados.
    auth_base_url: str = field(default_factory=lambda: os.getenv("AUTH_BASE_URL", "http://localhost:8800").rstrip("/"))
    api_base_url: str = field(default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:8800").rstrip("/"))

    # Identificador de la institución que aparece en el token (claim "tenantid").
    tenant_id: str = field(default_factory=lambda: os.getenv("TENANT_ID", "6c3d1a0e-0000-4000-8000-000000000001"))

    # Versiones de la API que anuncia el mock [APROX: D2L no publica cuál es la última].
    lp_versions: list[str] = field(default_factory=lambda: _versions("LP_VERSIONS", "1.46,1.47,1.48,1.49"))
    le_versions: list[str] = field(default_factory=lambda: _versions("LE_VERSIONS", "1.79,1.80,1.81,1.82"))

    # Límite de tasa por aplicación (token bucket) [APROX: D2L no publica los valores].
    rate_limit_capacity: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_CAPACITY", "300")))
    rate_limit_window_s: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW_S", "60")))

    # Tamaño de página de los listados paginados [APROX].
    page_size: int = field(default_factory=lambda: int(os.getenv("PAGE_SIZE", "100")))

    # ¿El scope core:*:* sirve para cualquier ruta? La doc dice que es el scope de respaldo para
    # acciones SIN scope específico. Por defecto el mock es estricto (False): si tu cliente funciona
    # así, también funcionará si Brightspace resulta más permisivo.
    core_scope_grants_all: bool = field(default_factory=lambda: _bool("CORE_SCOPE_GRANTS_ALL", False))

    # Brightspace exige que la URL JWKS sea HTTPS. Para pruebas locales el mock permite http:// y file://.
    allow_insecure_jwks: bool = field(default_factory=lambda: _bool("ALLOW_INSECURE_JWKS", True))

    # Límites de carga [DOC: 1 MB para JSON y 490 MB para binarios; en el mock son configurables].
    max_json_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_JSON_BYTES", str(1 * 1024 * 1024))))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))))

    # Vida del código de autorización y del refresh token [APROX].
    auth_code_ttl_s: int = 300
    refresh_token_ttl_s: int = field(default_factory=lambda: int(os.getenv("REFRESH_TOKEN_TTL_S", str(30 * 24 * 3600))))
    login_session_ttl_s: int = 8 * 3600

    # Cookie de sesión del navegador en la página de login: True si el mock corre detrás de HTTPS.
    cookie_secure: bool = field(default_factory=lambda: _bool("COOKIE_SECURE", False))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "brightspace_mock.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def token_endpoint(self) -> str:
        """URL exacta del endpoint de token: es el 'aud' que deben llevar las aserciones JWT."""
        return f"{self.auth_base_url}/core/connect/token"

    def versions_for(self, product: str) -> list[str]:
        return {"lp": self.lp_versions, "le": self.le_versions}.get(product, [])
