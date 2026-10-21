"""
Carpetas de entrega (dropbox), entregas y retroalimentación [DOC]. Base: /d2l/api/le/(version)/(orgUnitId)/dropbox

  GET  /folders/                                       dropbox:folders:read
  GET  /folders/(folderId)                             dropbox:folders:read
  POST /folders/                                       dropbox:folders:write
  PUT  /folders/(folderId)                             dropbox:folders:write
  GET  /folders/(folderId)/submissions/                dropbox:folders:read
  GET  /folders/(folderId)/submissions/paged/          dropbox:folders:read
  GET  /folders/(folderId)/submissions/mysubmissions/  dropbox:folders:read
  POST /folders/(folderId)/submissions/mysubmissions/  dropbox:folders:write  (multipart/mixed)
  GET  /folders/(folderId)/submissions/user/(userId)   dropbox:folders:read
  GET  /folders/(folderId)/submissions/(submissionId)/files/(fileId)  dropbox:folders:read
  GET  /folders/(folderId)/feedback/(entityType)/(entityId)           dropbox:folders:read
  POST /folders/(folderId)/feedback/(entityType)/(entityId)           dropbox:folders:write
"""
import json
import re
import sqlite3
from email import policy
from email.parser import BytesParser

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse

from app.api import formats
from app.api.common import is_number, read_json_body, set_grade_value
from app.api.deps import (MEMBERS, STAFF, STUDENT, Caller, check_version, get_conn, require_course_role,
                          require_scope)
from app.db import now_str, parse_d2l_date, utc_now
from app.errors import D2LError, bad_request, forbidden, not_found

router = APIRouter(dependencies=[Depends(check_version("le"))])
BASE = "/d2l/api/le/{version}/{org_unit_id:int}/dropbox/folders"

READ = require_scope("dropbox:folders:read")
WRITE = require_scope("dropbox:folders:write")


# ───────────────────────── consultas internas ─────────────────────────

def _folder(conn: sqlite3.Connection, org_unit_id: int, folder_id: int, role: str) -> sqlite3.Row:
    folder = conn.execute("SELECT * FROM dropbox_folders WHERE id = ? AND org_unit_id = ?",
                          (folder_id, org_unit_id)).fetchone()
    # Un estudiante no ve carpetas ocultas: para él no existen.
    if folder is None or (folder["is_hidden"] and role not in STAFF):
        raise not_found("Dropbox folder not found")
    return folder


def _students(conn: sqlite3.Connection, org_unit_id: int, after_id: int = 0, limit: int | None = None):
    sql = """SELECT u.* FROM enrollments e JOIN users u ON u.id = e.user_id JOIN roles r ON r.id = e.role_id
             WHERE e.org_unit_id = ? AND r.kind = 'student' AND u.is_active = 1 AND u.id > ? ORDER BY u.id"""
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, (org_unit_id, after_id)).fetchall()


def _counts(conn: sqlite3.Connection, folder: sqlite3.Row) -> dict:
    f = conn.execute(
        """SELECT COUNT(sf.id) AS files, COALESCE(SUM(sf.is_read = 0), 0) AS unread,
                  COALESCE(SUM(sf.is_flagged), 0) AS flagged
           FROM submissions s JOIN submission_files sf ON sf.submission_id = s.id WHERE s.folder_id = ?""",
        (folder["id"],)).fetchone()
    users = len(_students(conn, folder["org_unit_id"]))
    with_subs = conn.execute("SELECT COUNT(DISTINCT user_id) FROM submissions WHERE folder_id = ?",
                             (folder["id"],)).fetchone()[0]
    with_fb = conn.execute("SELECT COUNT(*) FROM dropbox_feedback WHERE folder_id = ? AND entity_type = 'user'",
                           (folder["id"],)).fetchone()[0]
    return {"files": f["files"], "unread": f["unread"], "flagged": f["flagged"], "users": users,
            "with_submissions": with_subs, "with_feedback": with_fb}


def _feedback_row(conn, folder_id: int, user_id: int):
    return conn.execute("SELECT * FROM dropbox_feedback WHERE folder_id = ? AND entity_type = 'user' AND entity_id = ?",
                        (folder_id, user_id)).fetchone()


def _entity(conn: sqlite3.Connection, folder_id: int, user: sqlite3.Row, *, staff_view: bool) -> dict:
    subs = conn.execute(
        """SELECT s.*, u.first_name || ' ' || u.last_name AS display_name FROM submissions s
           JOIN users u ON u.id = s.user_id WHERE s.folder_id = ? AND s.user_id = ? ORDER BY s.id""",
        (folder_id, user["id"])).fetchall()
    submissions = [
        formats.submission(s, conn.execute("SELECT * FROM submission_files WHERE submission_id = ? ORDER BY id",
                                           (s["id"],)).fetchall())
        for s in subs
    ]
    return formats.entity_dropbox(user, submissions, _feedback_row(conn, folder_id, user["id"]),
                                  show_draft_feedback=staff_view)


# ───────────────────────── validación de DropboxFolderUpdateData ─────────────────────────

def _date_field(data: dict, key: str):
    try:
        parse_d2l_date(data[key])
    except ValueError as exc:
        raise bad_request(f"{key}: {exc}")
    return data[key]


def _folder_changes(data, *, creating: bool, conn: sqlite3.Connection, org_unit_id: int) -> dict:
    """Traduce el JSON a columnas. En PUT, null o ausente deja el valor actual [DOC]."""
    if not isinstance(data, dict):
        raise bad_request("Expected a DropboxFolderUpdateData object")
    changes: dict = {}

    def present(key):
        return data.get(key) is not None

    if present("Name"):
        if not isinstance(data["Name"], str) or not data["Name"].strip():
            raise bad_request("Name must be a non-empty string")
        changes["name"] = data["Name"].strip()
    elif creating:
        raise bad_request("Name is required")

    if present("CustomInstructions"):
        try:
            changes["instructions_text"], changes["instructions_html"] = formats.read_rich_text_input(
                data["CustomInstructions"], "CustomInstructions")
        except ValueError as exc:
            raise bad_request(str(exc))

    if present("Availability"):
        availability = data["Availability"]
        if not isinstance(availability, dict):
            raise bad_request("Availability must be an object")
        for key, column in (("StartDate", "start_date"), ("EndDate", "end_date")):
            if availability.get(key) is not None:
                changes[column] = _date_field(availability, key)
    if present("DueDate"):
        changes["due_date"] = _date_field(data, "DueDate")

    for key, column in (("DisplayInCalendar", "display_in_calendar"), ("IsHidden", "is_hidden"),
                        ("IsAnonymous", "is_anonymous"), ("AllowOnlyUsersWithSpecialAccess", "allow_special_access")):
        if present(key):
            if not isinstance(data[key], bool):
                raise bad_request(f"{key} must be true or false")
            changes[column] = int(data[key])

    if present("NotificationEmail"):
        if not isinstance(data["NotificationEmail"], str):
            raise bad_request("NotificationEmail must be a string")
        changes["notification_email"] = data["NotificationEmail"]

    if present("Assessment"):
        assessment = data["Assessment"]
        if not isinstance(assessment, dict):
            raise bad_request("Assessment must be an object")
        if assessment.get("ScoreDenominator") is not None:
            if not is_number(assessment["ScoreDenominator"]) or assessment["ScoreDenominator"] <= 0:
                raise bad_request("Assessment.ScoreDenominator must be a positive number")
            changes["score_denominator"] = float(assessment["ScoreDenominator"])
        if assessment.get("Rubrics"):
            raise bad_request("Rubrics are not supported by this mock")

    enums = {"DropboxType": ("dropbox_type", {1, 2}), "SubmissionType": ("submission_type", {0, 1, 2, 3, 4}),
             "CompletionType": ("completion_type", {0, 1, 2, 3})}
    for key, (column, allowed) in enums.items():
        if present(key):
            if data[key] not in allowed or isinstance(data[key], bool):
                raise bad_request(f"{key} must be one of {sorted(allowed)}")
            changes[column] = data[key]
    if changes.get("dropbox_type") == 1 or present("GroupTypeId"):
        raise bad_request("Group folders are not supported by this mock")

    if present("SubmissionRule"):
        if data["SubmissionRule"] not in {"AllSubmissions", "OnlyOneSubmission", "OverwriteSubmissions"}:
            raise bad_request("SubmissionRule must be AllSubmissions, OnlyOneSubmission or OverwriteSubmissions")
        changes["submission_rule"] = data["SubmissionRule"]

    if present("GradeItemId"):
        exists = conn.execute("SELECT 1 FROM grade_objects WHERE id = ? AND org_unit_id = ?",
                              (data["GradeItemId"], org_unit_id)).fetchone()
        if not isinstance(data["GradeItemId"], int) or exists is None:
            raise bad_request("GradeItemId does not exist in this org unit")
        changes["grade_item_id"] = data["GradeItemId"]

    if present("CategoryId"):
        raise bad_request("Dropbox categories are not supported by this mock")
    return changes


# ───────────────────────── carpetas ─────────────────────────

@router.get(BASE + "/")
def list_folders(org_unit_id: int, conn: sqlite3.Connection = Depends(get_conn), caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    staff = role in STAFF
    rows = conn.execute("SELECT * FROM dropbox_folders WHERE org_unit_id = ? ORDER BY id", (org_unit_id,)).fetchall()
    return [formats.dropbox_folder(f, _counts(conn, f) if staff else None)
            for f in rows if staff or not f["is_hidden"]]


@router.get(BASE + "/{folder_id:int}")
def get_folder(org_unit_id: int, folder_id: int, conn: sqlite3.Connection = Depends(get_conn),
               caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    folder = _folder(conn, org_unit_id, folder_id, role)
    return formats.dropbox_folder(folder, _counts(conn, folder) if role in STAFF else None)


@router.post(BASE + "/")
async def create_folder(org_unit_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn),
                        caller: Caller = Depends(WRITE)):
    require_course_role(conn, caller, org_unit_id, STAFF)
    changes = _folder_changes(await read_json_body(request), creating=True, conn=conn, org_unit_id=org_unit_id)
    changes["org_unit_id"] = org_unit_id
    columns = ", ".join(changes)
    cursor = conn.execute(f"INSERT INTO dropbox_folders ({columns}) VALUES ({', '.join('?' * len(changes))})",
                          tuple(changes.values()))
    folder = conn.execute("SELECT * FROM dropbox_folders WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return formats.dropbox_folder(folder, _counts(conn, folder))


@router.put(BASE + "/{folder_id:int}")
async def update_folder(org_unit_id: int, folder_id: int, request: Request,
                        conn: sqlite3.Connection = Depends(get_conn), caller: Caller = Depends(WRITE)):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    _folder(conn, org_unit_id, folder_id, role)
    changes = _folder_changes(await read_json_body(request), creating=False, conn=conn, org_unit_id=org_unit_id)
    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        conn.execute(f"UPDATE dropbox_folders SET {assignments} WHERE id = ?", (*changes.values(), folder_id))
    folder = conn.execute("SELECT * FROM dropbox_folders WHERE id = ?", (folder_id,)).fetchone()
    return formats.dropbox_folder(folder, _counts(conn, folder))


# ───────────────────────── entregas ─────────────────────────

@router.get(BASE + "/{folder_id:int}/submissions/")
def list_submissions(org_unit_id: int, folder_id: int, conn: sqlite3.Connection = Depends(get_conn),
                     caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    _folder(conn, org_unit_id, folder_id, role)
    return [_entity(conn, folder_id, u, staff_view=True) for u in _students(conn, org_unit_id)]


@router.get(BASE + "/{folder_id:int}/submissions/paged/")
def list_submissions_paged(org_unit_id: int, folder_id: int, version: str, request: Request,
                           bookmark: str | None = None, activeOnly: str | None = None,
                           conn: sqlite3.Connection = Depends(get_conn), caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    _folder(conn, org_unit_id, folder_id, role)
    if activeOnly is not None and activeOnly.lower() not in {"true", "false"}:
        raise bad_request("activeOnly must be true or false")
    if bookmark not in (None, "") and not bookmark.isdigit():
        raise bad_request("Invalid bookmark")
    settings = request.app.state.settings
    users = _students(conn, org_unit_id, int(bookmark or 0), settings.page_size + 1)
    has_more = len(users) > settings.page_size
    users = users[:settings.page_size]
    next_url = formats.next_page_url(
        settings.api_base_url, f"/d2l/api/le/{version}/{org_unit_id}/dropbox/folders/{folder_id}/submissions/paged/",
        {"bookmark": users[-1]["id"], "activeOnly": activeOnly}) if has_more else None
    return formats.object_list_page([_entity(conn, folder_id, u, staff_view=True) for u in users], next_url)


@router.get(BASE + "/{folder_id:int}/submissions/mysubmissions/")
def my_submissions(org_unit_id: int, folder_id: int, conn: sqlite3.Connection = Depends(get_conn),
                   caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, STUDENT)
    _folder(conn, org_unit_id, folder_id, role)
    return [_entity(conn, folder_id, caller.user, staff_view=False)]


@router.get(BASE + "/{folder_id:int}/submissions/user/{user_id:int}")
def user_submissions(org_unit_id: int, folder_id: int, user_id: int, conn: sqlite3.Connection = Depends(get_conn),
                     caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    _folder(conn, org_unit_id, folder_id, role)
    student = next((u for u in _students(conn, org_unit_id) if u["id"] == user_id), None)
    if student is None:
        raise not_found("User is not a student in this org unit")
    return [_entity(conn, folder_id, student, staff_view=True)]


def _parse_multipart_mixed(content_type: str, body: bytes, max_json: int):
    """
    Cuerpo multipart/mixed de una entrega [DOC]:
      parte 1: application/json con un RichText (comentario)
      partes siguientes: archivos con Content-Disposition que trae filename
    """
    if not re.search(r"boundary=", content_type, re.I):
        raise bad_request("multipart/mixed requires a boundary")
    message = BytesParser(policy=policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    if not message.is_multipart():
        raise bad_request("Malformed multipart body")
    parts = list(message.iter_parts())
    if not parts:
        raise bad_request("Empty multipart body")

    first = parts[0]
    if first.get_content_type() != "application/json":
        raise bad_request("The first part must be application/json")
    raw_json = first.get_payload(decode=True) or b""
    if len(raw_json) > max_json:
        raise D2LError(413, "JSON part too large")
    try:
        comment = formats.read_rich_text_input(json.loads(raw_json or b"null"), "Comment")
    except ValueError as exc:
        raise bad_request(str(exc))

    files = []
    for part in parts[1:]:
        filename = part.get_filename()
        if not filename:
            raise bad_request("Each file part needs a Content-Disposition with filename")
        files.append((filename, part.get_content_type(), part.get_payload(decode=True) or b""))
    if not files:
        raise bad_request("A file is required")
    return comment, files


def _safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1].strip()
    return name or "archivo"


@router.post(BASE + "/{folder_id:int}/submissions/mysubmissions/")
async def submit(org_unit_id: int, folder_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn),
                 caller: Caller = Depends(WRITE)):
    role = require_course_role(conn, caller, org_unit_id, STUDENT)
    folder = _folder(conn, org_unit_id, folder_id, role)
    if not formats.is_open(folder, utc_now()):
        raise forbidden("The current user is not authorized to submit to this folder at this time.")
    if folder["submission_type"] not in (0, 4):
        raise D2LError(405, "This folder does not accept file submissions")

    settings = request.app.state.settings
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "multipart/mixed":
        raise D2LError(415, "Content-Type must be multipart/mixed")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes:
        raise D2LError(413, "Upload too large")
    body = await request.body()
    if len(body) > settings.max_upload_bytes:
        raise D2LError(413, "Upload too large")
    (comment_text, comment_html), files = _parse_multipart_mixed(content_type, body, settings.max_json_bytes)

    if folder["submission_rule"] == "OnlyOneSubmission":
        already = conn.execute("SELECT 1 FROM submissions WHERE folder_id = ? AND user_id = ?",
                               (folder_id, caller.id)).fetchone()
        if already:
            raise forbidden("Only one submission is allowed in this folder.")
    if folder["submission_rule"] == "OverwriteSubmissions":
        conn.execute("DELETE FROM submissions WHERE folder_id = ? AND user_id = ?", (folder_id, caller.id))

    cursor = conn.execute(
        "INSERT INTO submissions (folder_id, user_id, submitted_at, comment_text, comment_html) VALUES (?, ?, ?, ?, ?)",
        (folder_id, caller.id, now_str(), comment_text, comment_html))
    submission_id = cursor.lastrowid
    target_dir = settings.uploads_dir / str(submission_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename, file_type, data in files:
        file_cursor = conn.execute(
            "INSERT INTO submission_files (submission_id, file_name, content_type, size, storage_path) VALUES (?, ?, ?, ?, '')",
            (submission_id, _safe_filename(filename), file_type, len(data)))
        relative = f"{submission_id}/{file_cursor.lastrowid}"
        (settings.uploads_dir / relative).write_bytes(data)
        conn.execute("UPDATE submission_files SET storage_path = ? WHERE id = ?", (relative, file_cursor.lastrowid))
    return Response(status_code=200)  # [DOC] 200 sin cuerpo documentado


@router.get(BASE + "/{folder_id:int}/submissions/{submission_id:int}/files/{file_id:int}")
def download_file(org_unit_id: int, folder_id: int, submission_id: int, file_id: int, request: Request,
                  conn: sqlite3.Connection = Depends(get_conn), caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    _folder(conn, org_unit_id, folder_id, role)
    row = conn.execute(
        """SELECT sf.*, s.user_id FROM submission_files sf JOIN submissions s ON s.id = sf.submission_id
           WHERE sf.id = ? AND s.id = ? AND s.folder_id = ?""", (file_id, submission_id, folder_id)).fetchone()
    if row is None or (role not in STAFF and row["user_id"] != caller.id):
        raise not_found("File not found")
    path = request.app.state.settings.uploads_dir / row["storage_path"]
    return FileResponse(path, media_type=row["content_type"], filename=row["file_name"])


# ───────────────────────── retroalimentación ─────────────────────────

def _check_entity(conn, org_unit_id: int, entity_type: str, entity_id: int) -> sqlite3.Row:
    if entity_type == "group":
        raise not_found("Group entities are not supported by this mock")
    if entity_type != "user":
        raise not_found()
    student = next((u for u in _students(conn, org_unit_id) if u["id"] == entity_id), None)
    if student is None:
        raise not_found("Entity not found in this org unit")
    return student


@router.get(BASE + "/{folder_id:int}/feedback/{entity_type}/{entity_id:int}")
def get_feedback(org_unit_id: int, folder_id: int, entity_type: str, entity_id: int,
                 conn: sqlite3.Connection = Depends(get_conn), caller: Caller = Depends(READ)):
    role = require_course_role(conn, caller, org_unit_id, MEMBERS)
    _folder(conn, org_unit_id, folder_id, role)
    _check_entity(conn, org_unit_id, entity_type, entity_id)
    if role not in STAFF and entity_id != caller.id:
        raise forbidden("Not authorized to view this feedback")
    row = _feedback_row(conn, folder_id, entity_id)
    # El estudiante solo ve la retroalimentación publicada (IsGraded = true).
    if row is None or (role not in STAFF and not row["is_graded"]):
        raise not_found("No feedback")
    return formats.feedback_out(row)


@router.post(BASE + "/{folder_id:int}/feedback/{entity_type}/{entity_id:int}")
async def post_feedback(org_unit_id: int, folder_id: int, entity_type: str, entity_id: int, request: Request,
                        conn: sqlite3.Connection = Depends(get_conn), caller: Caller = Depends(WRITE)):
    role = require_course_role(conn, caller, org_unit_id, STAFF)
    folder = _folder(conn, org_unit_id, folder_id, role)
    _check_entity(conn, org_unit_id, entity_type, entity_id)
    data = await read_json_body(request)
    if not isinstance(data, dict):
        raise bad_request("Expected a DropboxFeedback object")

    score = data.get("Score")
    if score is not None and (not is_number(score) or score < 0):
        raise bad_request("Score must be a non-negative number or null")
    is_graded = data.get("IsGraded", False)
    if not isinstance(is_graded, bool):
        raise bad_request("IsGraded must be true or false")
    if data.get("RubricAssessments"):
        raise bad_request("RubricAssessments are not supported by this mock")
    if data.get("GradedSymbol") is not None:
        raise bad_request("GradedSymbol is not supported by this mock")
    try:
        text, html = formats.read_rich_text_input(data.get("Feedback"), "Feedback")
    except ValueError as exc:
        raise bad_request(str(exc))

    conn.execute(
        """INSERT INTO dropbox_feedback (folder_id, entity_type, entity_id, score, feedback_text, feedback_html, is_graded, updated_at)
           VALUES (?, 'user', ?, ?, ?, ?, ?, ?)
           ON CONFLICT (folder_id, entity_type, entity_id) DO UPDATE SET score = excluded.score,
             feedback_text = excluded.feedback_text, feedback_html = excluded.feedback_html,
             is_graded = excluded.is_graded, updated_at = excluded.updated_at""",
        (folder_id, entity_id, score, text, html, int(is_graded), now_str()))

    # [APROX] Al publicar con nota en una carpeta enlazada a un ítem de calificación, la nota pasa
    # al libro de calificaciones (así se comporta la interfaz de Brightspace).
    if is_graded and score is not None and folder["grade_item_id"]:
        grade_obj = conn.execute("SELECT * FROM grade_objects WHERE id = ?", (folder["grade_item_id"],)).fetchone()
        denominator = folder["score_denominator"] or grade_obj["max_points"]
        points = round(score / denominator * grade_obj["max_points"], 4)
        set_grade_value(conn, grade_object_id=grade_obj["id"], user_id=entity_id, points=points,
                        modified_by=caller.id, comments=(text, html))
    return Response(status_code=200)
