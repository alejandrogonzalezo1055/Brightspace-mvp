"""
Base de datos SQLite del mock (módulo sqlite3 de la librería estándar).

Cada petición abre su propia conexión: SQLite es un archivo local y abrirlo es barato, y así no
hay que compartir una conexión entre hilos.
"""
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS org_unit_types (
    id   INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS org_units (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id    INTEGER NOT NULL REFERENCES org_unit_types(id),
    name       TEXT NOT NULL,
    code       TEXT,
    is_active  INTEGER NOT NULL DEFAULT 1,
    start_date TEXT,
    end_date   TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    id   INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('instructor', 'student', 'admin', 'service', 'user'))
);

CREATE TABLE IF NOT EXISTS users (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    username           TEXT NOT NULL UNIQUE,
    first_name         TEXT NOT NULL,
    last_name          TEXT NOT NULL,
    email              TEXT,
    org_defined_id     TEXT,
    profile_identifier TEXT NOT NULL,
    password_hash      TEXT,           -- NULL para usuarios de servicio (no inician sesión)
    is_active          INTEGER NOT NULL DEFAULT 1,
    org_role_id        INTEGER NOT NULL REFERENCES roles(id),
    created_at         TEXT NOT NULL,
    last_accessed      TEXT
);

CREATE TABLE IF NOT EXISTS enrollments (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_unit_id INTEGER NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
    role_id     INTEGER NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, org_unit_id)
);

-- ───────── OAuth 2.0 ─────────
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    grant_type      TEXT NOT NULL CHECK (grant_type IN ('authorization_code', 'client_credentials')),
    secret_hash     TEXT,              -- solo authorization_code
    redirect_uri    TEXT,              -- solo authorization_code
    jwks_url        TEXT,              -- solo client_credentials
    service_user_id INTEGER REFERENCES users(id),
    scopes          TEXT NOT NULL,
    token_lifetime  INTEGER NOT NULL,
    refresh_enabled INTEGER NOT NULL DEFAULT 0,
    prompt_consent  INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_consents (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, client_id)
);

-- Se guarda el hash SHA-256, nunca el código o el token en claro.
CREATE TABLE IF NOT EXISTS oauth_codes (
    code_hash    TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    scope        TEXT NOT NULL,
    expires_at   REAL NOT NULL,
    used         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
    token_hash TEXT PRIMARY KEY,
    client_id  TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope      TEXT NOT NULL,
    expires_at REAL NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oauth_used_jti (
    client_id  TEXT NOT NULL,
    jti        TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (client_id, jti)
);

CREATE TABLE IF NOT EXISTS login_sessions (
    session_hash TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token   TEXT NOT NULL,
    expires_at   REAL NOT NULL
);

-- ───────── Carpetas de entrega (dropbox) ─────────
CREATE TABLE IF NOT EXISTS grade_objects (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    org_unit_id        INTEGER NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
    name               TEXT NOT NULL,
    short_name         TEXT NOT NULL DEFAULT '',
    max_points         REAL NOT NULL,
    can_exceed         INTEGER NOT NULL DEFAULT 0,
    is_bonus           INTEGER NOT NULL DEFAULT 0,
    exclude_from_final INTEGER NOT NULL DEFAULT 0,
    description        TEXT NOT NULL DEFAULT '',
    is_hidden          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dropbox_folders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    org_unit_id          INTEGER NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
    name                 TEXT NOT NULL,
    instructions_text    TEXT NOT NULL DEFAULT '',
    instructions_html    TEXT,
    start_date           TEXT,
    end_date             TEXT,
    due_date             TEXT,
    display_in_calendar  INTEGER NOT NULL DEFAULT 0,
    notification_email   TEXT,
    is_hidden            INTEGER NOT NULL DEFAULT 0,
    score_denominator    REAL,
    is_anonymous         INTEGER NOT NULL DEFAULT 0,
    dropbox_type         INTEGER NOT NULL DEFAULT 2,
    submission_type      INTEGER NOT NULL DEFAULT 0,
    completion_type      INTEGER NOT NULL DEFAULT 0,
    submission_rule      TEXT NOT NULL DEFAULT 'AllSubmissions',
    grade_item_id        INTEGER REFERENCES grade_objects(id) ON DELETE SET NULL,
    category_id          INTEGER,
    allow_special_access INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id     INTEGER NOT NULL REFERENCES dropbox_folders(id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    submitted_at  TEXT NOT NULL,
    comment_text  TEXT NOT NULL DEFAULT '',
    comment_html  TEXT
);

CREATE TABLE IF NOT EXISTS submission_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    file_name     TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    size          INTEGER NOT NULL,
    storage_path  TEXT NOT NULL,
    is_read       INTEGER NOT NULL DEFAULT 0,
    is_flagged    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dropbox_feedback (
    folder_id     INTEGER NOT NULL REFERENCES dropbox_folders(id) ON DELETE CASCADE,
    entity_type   TEXT NOT NULL CHECK (entity_type IN ('user', 'group')),
    entity_id     INTEGER NOT NULL,
    score         REAL,
    feedback_text TEXT NOT NULL DEFAULT '',
    feedback_html TEXT,
    is_graded     INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (folder_id, entity_type, entity_id)
);

-- ───────── Libro de calificaciones ─────────
CREATE TABLE IF NOT EXISTS grade_values (
    grade_object_id  INTEGER NOT NULL REFERENCES grade_objects(id) ON DELETE CASCADE,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    points           REAL NOT NULL,
    comments_text    TEXT NOT NULL DEFAULT '',
    comments_html    TEXT,
    private_text     TEXT NOT NULL DEFAULT '',
    private_html     TEXT,
    last_modified    TEXT NOT NULL,
    last_modified_by INTEGER,
    released_date    TEXT,
    PRIMARY KEY (grade_object_id, user_id)
);
"""


_D2L_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_d2l_date(value: datetime | None) -> str | None:
    """Formato UTCDateTime de D2L: yyyy-MM-ddTHH:mm:ss.fffZ [DOC]."""
    if value is None:
        return None
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def parse_d2l_date(value: str | None) -> datetime | None:
    """Acepta solo el formato UTCDateTime documentado; cualquier otro lanza ValueError."""
    if value is None:
        return None
    if not isinstance(value, str) or not _D2L_DATE.fullmatch(value):
        raise ValueError(f"fecha inválida: se espera yyyy-MM-ddTHH:mm:ss.fffZ, llegó {value!r}")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def now_str() -> str:
    return to_d2l_date(utc_now())


def connect(db_path: Path) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI puede crear la conexión en un hilo y usarla en otro dentro de la
    # MISMA petición. Nunca se comparte entre peticiones, así que es seguro.
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_path: Path):
    """Abre una conexión, hace commit si todo sale bien y rollback si hay excepción."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
