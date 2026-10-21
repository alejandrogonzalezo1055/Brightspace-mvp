"""Utilidades compartidas por las rutas de carpetas de entrega y de calificaciones."""
import json
import sqlite3

from fastapi import Request

from app.db import now_str
from app.errors import D2LError, bad_request


async def read_json_body(request: Request):
    """Lee el cuerpo JSON aplicando las reglas de la API: 415 si no es JSON, 413 si es enorme, 400 si no parsea."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise D2LError(415, "Content-Type must be application/json")
    body = await request.body()
    if len(body) > request.app.state.settings.max_json_bytes:
        raise D2LError(413, "JSON body too large")
    try:
        return json.loads(body)
    except ValueError:
        raise bad_request("Invalid JSON")


def set_grade_value(conn: sqlite3.Connection, *, grade_object_id: int, user_id: int, points: float,
                    modified_by: int, comments: tuple[str, str | None] | None = None,
                    private: tuple[str, str | None] | None = None) -> None:
    """Crea o reemplaza la nota de un estudiante en un ítem. En el mock la nota queda publicada de una vez [APROX]."""
    now = now_str()
    existing = conn.execute("SELECT * FROM grade_values WHERE grade_object_id = ? AND user_id = ?",
                            (grade_object_id, user_id)).fetchone()
    comments_text, comments_html = comments if comments is not None else (
        (existing["comments_text"], existing["comments_html"]) if existing else ("", None))
    private_text, private_html = private if private is not None else (
        (existing["private_text"], existing["private_html"]) if existing else ("", None))
    conn.execute(
        """INSERT INTO grade_values (grade_object_id, user_id, points, comments_text, comments_html,
                                     private_text, private_html, last_modified, last_modified_by, released_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (grade_object_id, user_id) DO UPDATE SET
             points = excluded.points, comments_text = excluded.comments_text, comments_html = excluded.comments_html,
             private_text = excluded.private_text, private_html = excluded.private_html,
             last_modified = excluded.last_modified, last_modified_by = excluded.last_modified_by,
             released_date = excluded.released_date""",
        (grade_object_id, user_id, points, comments_text, comments_html, private_text, private_html,
         now, modified_by, now),
    )


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
