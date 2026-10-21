"""
Dependencias compartidas por todas las rutas /d2l/api/...:

- get_conn:        una conexión SQLite con transacción por petición.
- current_caller:  quién llama, sacado del access token (403 "Invalid Token" si no sirve) [DOC].
- require_scope:   el token debe tener el scope que exige la ruta (403 si no) [DOC].
- check_version:   la versión de la ruta (p. ej. 1.49) debe estar soportada (404 si no) [APROX].
- course_role:     qué rol tiene el usuario en un curso (los permisos por rol son [APROX]).
"""
import sqlite3
from dataclasses import dataclass

from fastapi import Depends, Request

from app.db import transaction
from app.errors import D2LError, forbidden, invalid_token, not_found
from app.security import scopes as scope_rules


def get_conn(request: Request):
    with transaction(request.app.state.settings.db_path) as conn:
        yield conn


@dataclass
class Caller:
    user: sqlite3.Row
    scope: str
    client_id: str
    org_role_kind: str  # 'admin', 'service' o 'user'

    @property
    def id(self) -> int:
        return self.user["id"]

    @property
    def is_privileged(self) -> bool:
        """Administrador de la organización o usuario de servicio: ve todos los cursos."""
        return self.org_role_kind in {"admin", "service"}


def current_caller(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Caller:
    claims = getattr(request.state, "token_claims", None)
    if not claims:
        raise invalid_token()
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise invalid_token()
    user = conn.execute(
        """SELECT u.*, r.kind AS org_role_kind FROM users u JOIN roles r ON r.id = u.org_role_id
           WHERE u.id = ? AND u.is_active = 1""",
        (user_id,),
    ).fetchone()
    if user is None:
        raise invalid_token()
    kind = user["org_role_kind"] if user["org_role_kind"] in {"admin", "service"} else "user"
    return Caller(user=user, scope=claims["scope"], client_id=claims["azp"], org_role_kind=kind)


def require_scope(*any_of: str):
    """Fábrica de dependencias: Depends(require_scope('dropbox:folders:read'))."""

    def checker(request: Request, caller: Caller = Depends(current_caller)) -> Caller:
        settings = request.app.state.settings
        if not scope_rules.satisfies(caller.scope, any_of, settings.core_scope_grants_all):
            raise forbidden(f"Insufficient scope. Required: {' or '.join(any_of)}")
        return caller

    return checker


def check_version(product: str):
    def checker(request: Request, version: str) -> str:
        if version not in request.app.state.settings.versions_for(product):
            raise D2LError(404, f"Unsupported API version {product}/{version}")
        return version

    return checker


def get_org_unit(conn: sqlite3.Connection, org_unit_id: int) -> sqlite3.Row:
    ou = conn.execute(
        "SELECT ou.*, t.code AS type_code, t.name AS type_name FROM org_units ou "
        "JOIN org_unit_types t ON t.id = ou.type_id WHERE ou.id = ?", (org_unit_id,)
    ).fetchone()
    if ou is None:
        raise not_found("Org unit not found")
    return ou


def course_role(conn: sqlite3.Connection, caller: Caller, org_unit_id: int) -> str | None:
    """'staff' (admin o servicio), 'instructor', 'student' o None si no está en el curso."""
    get_org_unit(conn, org_unit_id)  # 404 si el curso no existe
    if caller.is_privileged:
        return "staff"
    row = conn.execute(
        "SELECT r.kind FROM enrollments e JOIN roles r ON r.id = e.role_id WHERE e.user_id = ? AND e.org_unit_id = ?",
        (caller.id, org_unit_id),
    ).fetchone()
    return row["kind"] if row else None


def require_course_role(conn: sqlite3.Connection, caller: Caller, org_unit_id: int, allowed: set[str]) -> str:
    role = course_role(conn, caller, org_unit_id)
    if role not in allowed:
        raise forbidden("The current user context does not have permission for this action in this org unit.")
    return role


# Atajos de lectura para las rutas.
STAFF = {"instructor", "staff"}            # docente del curso, admin o usuario de servicio
MEMBERS = {"instructor", "student", "staff"}
STUDENT = {"student"}
