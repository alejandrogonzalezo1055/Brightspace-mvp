"""
Libro de calificaciones [DOC]. Base: /d2l/api/le/(version)/(orgUnitId)/grades

  GET /                                   grades:gradeobjects:read
  GET /(gradeObjectId)                    grades:gradeobjects:read
  GET /(gradeObjectId)/values/            grades:gradevalues:read
  GET /(gradeObjectId)/values/(userId)    grades:gradevalues:read
  PUT /(gradeObjectId)/values/(userId)    grades:gradevalues:write
  GET /(gradeObjectId)/values/myGradeValue   grades:own_grades:read
  GET /values/myGradeValues/              grades:own_grades:read
  GET /final/values/myGradeValue          grades:own_grades:read
"""
import sqlite3

from fastapi import APIRouter, Depends, Request, Response

from app.api import formats
from app.api.common import is_number, read_json_body, set_grade_value
from app.api.deps import MEMBERS, STAFF, STUDENT, Caller, check_version, get_conn, require_course_role, require_scope
from app.errors import bad_request, not_found

router = APIRouter(dependencies=[Depends(check_version("le"))])
BASE = "/d2l/api/le/{version}/{org_unit_id:int}/grades"


def _grade_object(conn: sqlite3.Connection, org_unit_id: int, grade_object_id: int, role: str) -> sqlite3.Row:
    go = conn.execute("SELECT * FROM grade_objects WHERE id = ? AND org_unit_id = ?",
                      (grade_object_id, org_unit_id)).fetchone()
    if go is None or (go["is_hidden"] and role not in STAFF):
        raise not_found("Grade object not found")
    return go


def _linked_folder(conn: sqlite3.Connection, grade_object_id: int) -> int | None:
    row = conn.execute("SELECT id FROM dropbox_folders WHERE grade_item_id = ? ORDER BY id LIMIT 1",
                       (grade_object_id,)).fetchone()
    return row["id"] if row else None


@router.get(BASE + "/")
def list_grade_objects(org_unit_id: int, version: str, conn: sqlite3.Connection = Depends(get_conn),
                       caller: Caller = Depends(require_scope("grades:gradeobjects:read"))):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    rows = conn.execute("SELECT * FROM grade_objects WHERE org_unit_id = ? ORDER BY id", (org_unit_id,)).fetchall()
    return [formats.grade_object(go, version, associated_folder_id=_linked_folder(conn, go["id"]))
            for go in rows if role in STAFF or not go["is_hidden"]]


# Las rutas con segmentos fijos (values/myGradeValues, final/...) van antes que /{gradeObjectId}.

@router.get(BASE + "/values/myGradeValues/")
def my_grade_values(org_unit_id: int, conn: sqlite3.Connection = Depends(get_conn),
                    caller: Caller = Depends(require_scope("grades:own_grades:read"))):
    require_course_role(conn, caller, org_unit_id, STUDENT)
    rows = conn.execute(
        """SELECT gv.*, go.id AS go_id FROM grade_values gv JOIN grade_objects go ON go.id = gv.grade_object_id
           WHERE go.org_unit_id = ? AND gv.user_id = ? AND go.is_hidden = 0 AND gv.released_date IS NOT NULL
           ORDER BY go.id""", (org_unit_id, caller.id)).fetchall()
    result = []
    for gv in rows:
        go = conn.execute("SELECT * FROM grade_objects WHERE id = ?", (gv["go_id"],)).fetchone()
        result.append(formats.grade_value(gv, go, include_private=False))
    return result


@router.get(BASE + "/final/values/myGradeValue")
def my_final_grade(org_unit_id: int, conn: sqlite3.Connection = Depends(get_conn),
                   caller: Caller = Depends(require_scope("grades:own_grades:read"))):
    require_course_role(conn, caller, org_unit_id, STUDENT)
    row = conn.execute(
        """SELECT SUM(gv.points) AS points, SUM(go.max_points) AS max_points, MAX(gv.last_modified) AS last_modified
           FROM grade_values gv JOIN grade_objects go ON go.id = gv.grade_object_id
           WHERE go.org_unit_id = ? AND gv.user_id = ? AND go.is_hidden = 0 AND go.exclude_from_final = 0
             AND go.is_bonus = 0 AND gv.released_date IS NOT NULL""", (org_unit_id, caller.id)).fetchone()
    if row["points"] is None:
        raise not_found("No final grade yet")
    return formats.final_grade_value(row["points"], row["max_points"], row["last_modified"])


@router.get(BASE + "/{grade_object_id:int}")
def get_grade_object(org_unit_id: int, grade_object_id: int, version: str,
                     conn: sqlite3.Connection = Depends(get_conn),
                     caller: Caller = Depends(require_scope("grades:gradeobjects:read"))):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    go = _grade_object(conn, org_unit_id, grade_object_id, role)
    return formats.grade_object(go, version, associated_folder_id=_linked_folder(conn, go["id"]))


@router.get(BASE + "/{grade_object_id:int}/values/")
def list_grade_values(org_unit_id: int, grade_object_id: int, version: str, request: Request,
                      isGraded: str | None = None, searchText: str | None = None, pageSize: int | None = None,
                      bookmark: str | None = None, conn: sqlite3.Connection = Depends(get_conn),
                      caller: Caller = Depends(require_scope("grades:gradevalues:read"))):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    go = _grade_object(conn, org_unit_id, grade_object_id, role)
    if isGraded is not None and isGraded.lower() not in {"true", "false"}:
        raise bad_request("isGraded must be true or false")
    if pageSize is not None and not 1 <= pageSize <= 200:
        raise bad_request("pageSize must be between 1 and 200")
    if bookmark not in (None, "") and not bookmark.isdigit():
        raise bad_request("Invalid bookmark")
    size = pageSize or request.app.state.settings.page_size

    sql = """SELECT u.* FROM enrollments e JOIN users u ON u.id = e.user_id JOIN roles r ON r.id = e.role_id
             WHERE e.org_unit_id = ? AND r.kind = 'student' AND u.is_active = 1 AND u.id > ?"""
    params: list = [org_unit_id, int(bookmark or 0)]
    if searchText:
        sql += " AND (u.first_name LIKE ? OR u.last_name LIKE ? OR u.username LIKE ?)"
        params += [f"%{searchText}%"] * 3
    if isGraded is not None:
        op = "EXISTS" if isGraded.lower() == "true" else "NOT EXISTS"
        sql += f" AND {op} (SELECT 1 FROM grade_values gv WHERE gv.user_id = u.id AND gv.grade_object_id = ?)"
        params.append(grade_object_id)
    students = conn.execute(sql + " ORDER BY u.id LIMIT ?", (*params, size + 1)).fetchall()
    has_more = len(students) > size
    students = students[:size]

    objects = []
    for user in students:
        gv = conn.execute("SELECT * FROM grade_values WHERE grade_object_id = ? AND user_id = ?",
                          (grade_object_id, user["id"])).fetchone()
        objects.append({"User": formats.user_composite(user),
                        "GradeValue": formats.grade_value(gv, go, include_private=True) if gv else None})
    next_url = formats.next_page_url(
        request.app.state.settings.api_base_url,
        f"/d2l/api/le/{version}/{org_unit_id}/grades/{grade_object_id}/values/",
        {"bookmark": students[-1]["id"], "isGraded": isGraded, "searchText": searchText, "pageSize": pageSize},
    ) if has_more else None
    return formats.object_list_page(objects, next_url)


@router.get(BASE + "/{grade_object_id:int}/values/myGradeValue")
def my_grade_value(org_unit_id: int, grade_object_id: int, conn: sqlite3.Connection = Depends(get_conn),
                   caller: Caller = Depends(require_scope("grades:own_grades:read"))):
    role = require_course_role(conn, caller, org_unit_id, STUDENT)
    go = _grade_object(conn, org_unit_id, grade_object_id, role)
    gv = conn.execute("SELECT * FROM grade_values WHERE grade_object_id = ? AND user_id = ? AND released_date IS NOT NULL",
                      (grade_object_id, caller.id)).fetchone()
    if gv is None:
        raise not_found("No grade value")
    return formats.grade_value(gv, go, include_private=False)


def _student_in_course(conn, org_unit_id: int, user_id: int) -> None:
    row = conn.execute(
        """SELECT 1 FROM enrollments e JOIN roles r ON r.id = e.role_id
           WHERE e.org_unit_id = ? AND e.user_id = ? AND r.kind = 'student'""", (org_unit_id, user_id)).fetchone()
    if row is None:
        raise not_found("User is not a student in this org unit")


@router.get(BASE + "/{grade_object_id:int}/values/{user_id:int}")
def get_grade_value(org_unit_id: int, grade_object_id: int, user_id: int, conn: sqlite3.Connection = Depends(get_conn),
                    caller: Caller = Depends(require_scope("grades:gradevalues:read"))):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    go = _grade_object(conn, org_unit_id, grade_object_id, role)
    _student_in_course(conn, org_unit_id, user_id)
    gv = conn.execute("SELECT * FROM grade_values WHERE grade_object_id = ? AND user_id = ?",
                      (grade_object_id, user_id)).fetchone()
    if gv is None:
        raise not_found("No grade value")
    return formats.grade_value(gv, go, include_private=True)


@router.put(BASE + "/{grade_object_id:int}/values/{user_id:int}")
async def put_grade_value(org_unit_id: int, grade_object_id: int, user_id: int, request: Request,
                          conn: sqlite3.Connection = Depends(get_conn),
                          caller: Caller = Depends(require_scope("grades:gradevalues:write"))):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    go = _grade_object(conn, org_unit_id, grade_object_id, role)
    _student_in_course(conn, org_unit_id, user_id)
    data = await read_json_body(request)
    if not isinstance(data, dict):
        raise bad_request("Expected an IncomingGradeValue object")
    # IncomingGradeValue numérico [DOC]: GradeObjectType 1 + PointsNumerator (+ comentarios opcionales).
    if data.get("GradeObjectType") != 1:
        raise bad_request("GradeObjectType must be 1 (Numeric)")
    points = data.get("PointsNumerator")
    if not is_number(points) or points < 0:
        raise bad_request("PointsNumerator must be a non-negative number")
    if points > go["max_points"] and not go["can_exceed"]:
        raise bad_request("PointsNumerator exceeds MaxPoints for this grade object")
    try:
        comments = formats.read_rich_text_input(data["Comments"], "Comments") if "Comments" in data else None
        private = formats.read_rich_text_input(data["PrivateComments"], "PrivateComments") if "PrivateComments" in data else None
    except ValueError as exc:
        raise bad_request(str(exc))
    set_grade_value(conn, grade_object_id=grade_object_id, user_id=user_id, points=float(points),
                    modified_by=caller.id, comments=comments, private=private)
    return Response(status_code=200)  # [APROX] cuerpo de respuesta no documentado
