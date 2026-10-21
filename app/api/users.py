"""
Usuarios [DOC]:

  GET /d2l/api/lp/(version)/users/whoami     scope users:profile:read o users:own_profile:read
  GET /d2l/api/lp/(version)/users/(userId)   scope users:userdata:read
"""
import sqlite3

from fastapi import APIRouter, Depends

from app.api import formats
from app.api.deps import Caller, check_version, get_conn, require_scope
from app.errors import forbidden, not_found

router = APIRouter(dependencies=[Depends(check_version("lp"))])


def org_id(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT id FROM org_units WHERE type_id = 1 ORDER BY id LIMIT 1").fetchone()["id"]


@router.get("/d2l/api/lp/{version}/users/whoami")
def who_am_i(caller: Caller = Depends(require_scope("users:profile:read", "users:own_profile:read"))):
    return formats.who_am_i(caller.user)


@router.get("/d2l/api/lp/{version}/users/{user_id:int}")
def get_user(user_id: int, conn: sqlite3.Connection = Depends(get_conn),
             caller: Caller = Depends(require_scope("users:userdata:read"))):
    user = conn.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
    if user is None:
        raise not_found()
    # [APROX] Permiso para ver usuarios: admin/servicio ven a todos; un docente ve a quienes están en
    # sus cursos; cualquiera se ve a sí mismo.
    if not caller.is_privileged and user_id != caller.id:
        shared = conn.execute(
            """SELECT 1 FROM enrollments mine JOIN roles r ON r.id = mine.role_id
               JOIN enrollments theirs ON theirs.org_unit_id = mine.org_unit_id
               WHERE mine.user_id = ? AND r.kind = 'instructor' AND theirs.user_id = ? LIMIT 1""",
            (caller.id, user_id),
        ).fetchone()
        if shared is None:
            raise forbidden("Not authorized to view this user")
    return formats.user_data(user, org_id(conn))
