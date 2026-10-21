"""
Inscripciones y lista de clase [DOC]:

  GET /d2l/api/lp/(v)/enrollments/myenrollments/              enrollment:own_enrollment:read
  GET /d2l/api/lp/(v)/enrollments/orgUnits/(orgUnitId)/users/ enrollment:orgunit:read
  GET /d2l/api/le/(v)/(orgUnitId)/classlist/                  enrollment:orgunit:read
  GET /d2l/api/le/(v)/(orgUnitId)/classlist/paged/            enrollment:orgunit:read
"""
import sqlite3

from fastapi import APIRouter, Depends, Request

from app.api import formats
from app.api.deps import MEMBERS, STAFF, Caller, check_version, get_conn, require_course_role, require_scope
from app.errors import bad_request

lp = APIRouter(dependencies=[Depends(check_version("lp"))])
le = APIRouter(dependencies=[Depends(check_version("le"))])


def _bookmark(value: str | None) -> int:
    if value in (None, ""):
        return 0
    if not value.isdigit():
        raise bad_request("Invalid bookmark")
    return int(value)


def _bool_param(value: str | None, name: str) -> bool | None:
    if value is None:
        return None
    if value.lower() not in {"true", "false"}:
        raise bad_request(f"{name} must be true or false")
    return value.lower() == "true"


@lp.get("/d2l/api/lp/{version}/enrollments/myenrollments/")
def my_enrollments(request: Request, orgUnitTypeId: int | None = None, bookmark: str | None = None,
                   isActive: str | None = None, canAccess: str | None = None,
                   conn: sqlite3.Connection = Depends(get_conn),
                   caller: Caller = Depends(require_scope("enrollment:own_enrollment:read"))):
    page_size = request.app.state.settings.page_size
    sql = """SELECT ou.*, t.code AS type_code, t.name AS type_name, r.name AS role_name, r.kind AS role_kind
             FROM enrollments e JOIN org_units ou ON ou.id = e.org_unit_id
             JOIN org_unit_types t ON t.id = ou.type_id JOIN roles r ON r.id = e.role_id
             WHERE e.user_id = ? AND ou.id > ?"""
    params: list = [caller.id, _bookmark(bookmark)]
    if orgUnitTypeId is not None:
        sql += " AND ou.type_id = ?"
        params.append(orgUnitTypeId)
    active = _bool_param(isActive, "isActive")
    if active is None:
        active = _bool_param(canAccess, "canAccess")  # en el mock, acceder = estar activo
    if active is not None:
        sql += " AND ou.is_active = ?"
        params.append(int(active))
    rows = conn.execute(sql + " ORDER BY ou.id LIMIT ?", (*params, page_size + 1)).fetchall()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    return formats.paged_result_set([formats.my_org_unit_info(r) for r in rows], has_more,
                                    str(rows[-1]["id"]) if has_more else None)


@lp.get("/d2l/api/lp/{version}/enrollments/orgUnits/{org_unit_id:int}/users/")
def org_unit_users(org_unit_id: int, request: Request, roleId: int | None = None, isActive: str | None = None,
                   bookmark: str | None = None, conn: sqlite3.Connection = Depends(get_conn),
                   caller: Caller = Depends(require_scope("enrollment:orgunit:read"))):
    require_course_role(conn, caller, org_unit_id, STAFF)
    page_size = request.app.state.settings.page_size
    sql = """SELECT u.*, r.id AS r_id, r.code AS r_code, r.name AS r_name FROM enrollments e
             JOIN users u ON u.id = e.user_id JOIN roles r ON r.id = e.role_id
             WHERE e.org_unit_id = ? AND u.id > ?"""
    params: list = [org_unit_id, _bookmark(bookmark)]
    if roleId is not None:
        sql += " AND e.role_id = ?"
        params.append(roleId)
    active = _bool_param(isActive, "isActive")
    if active is not None:
        sql += " AND u.is_active = ?"
        params.append(int(active))
    rows = conn.execute(sql + " ORDER BY u.id LIMIT ?", (*params, page_size + 1)).fetchall()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    items = [{"User": formats.user_composite(r), "Role": {"Id": r["r_id"], "Code": r["r_code"], "Name": r["r_name"]}}
             for r in rows]
    return formats.paged_result_set(items, has_more, str(rows[-1]["id"]) if has_more else None)


def _classlist_rows(conn, org_unit_id: int, role_id: int | None, search: str | None, after_id: int, limit: int | None):
    sql = """SELECT u.*, e.role_id, r.name AS role_name FROM enrollments e
             JOIN users u ON u.id = e.user_id JOIN roles r ON r.id = e.role_id
             WHERE e.org_unit_id = ? AND u.is_active = 1 AND u.id > ?"""
    params: list = [org_unit_id, after_id]
    if role_id is not None:
        sql += " AND e.role_id = ?"
        params.append(role_id)
    if search:
        sql += " AND (u.first_name LIKE ? OR u.last_name LIKE ? OR u.username LIKE ? OR u.org_defined_id LIKE ?)"
        params += [f"%{search}%"] * 4
    sql += " ORDER BY u.id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, params).fetchall()


@le.get("/d2l/api/le/{version}/{org_unit_id:int}/classlist/")
def classlist(org_unit_id: int, conn: sqlite3.Connection = Depends(get_conn),
              caller: Caller = Depends(require_scope("enrollment:orgunit:read"))):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    rows = _classlist_rows(conn, org_unit_id, None, None, 0, None)
    return [formats.classlist_user(r, full=role in STAFF) for r in rows]


@le.get("/d2l/api/le/{version}/{org_unit_id:int}/classlist/paged/")
def classlist_paged(org_unit_id: int, version: str, request: Request, roleId: int | None = None,
                    searchTerm: str | None = None, onlyShowShownInGrades: str | None = None,
                    bookmark: str | None = None, conn: sqlite3.Connection = Depends(get_conn),
                    caller: Caller = Depends(require_scope("enrollment:orgunit:read"))):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    _bool_param(onlyShowShownInGrades, "onlyShowShownInGrades")  # se valida; el mock muestra a todos
    settings = request.app.state.settings
    rows = _classlist_rows(conn, org_unit_id, roleId, searchTerm, _bookmark(bookmark), settings.page_size + 1)
    has_more = len(rows) > settings.page_size
    rows = rows[:settings.page_size]
    next_url = formats.next_page_url(
        settings.api_base_url, f"/d2l/api/le/{version}/{org_unit_id}/classlist/paged/",
        {"roleId": roleId, "searchTerm": searchTerm, "bookmark": rows[-1]["id"]},
    ) if has_more else None
    return formats.object_list_page([formats.classlist_user(r, full=role in STAFF) for r in rows], next_url)
