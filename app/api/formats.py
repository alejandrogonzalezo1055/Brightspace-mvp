"""
Conversión de filas de la base a las estructuras JSON de Brightspace.

Los nombres y el orden de los campos siguen la documentación de D2L [DOC]. Lo marcado [APROX] es
un valor que el mock rellena porque no maneja esa funcionalidad (p. ej. rúbricas o grupos).
"""
import re
import sqlite3
from urllib.parse import urlencode

from app.db import parse_d2l_date


def rich_text(text: str | None, html: str | None) -> dict:
    """RichText de salida [DOC]: {"Text": ..., "Html": ...}; Html puede ser null."""
    return {"Text": text or "", "Html": html}


def read_rich_text_input(value, field: str) -> tuple[str, str | None]:
    """
    Acepta RichTextInput [DOC] {"Content", "Type": "Text"|"Html"} y, por tolerancia, RichText {"Text", "Html"}.
    Devuelve (texto, html). Lanza ValueError si la forma no es válida.
    """
    if value is None:
        return "", None
    if not isinstance(value, dict):
        raise ValueError(f"{field} debe ser un objeto RichTextInput")
    if "Content" in value:
        kind = value.get("Type")
        content = value.get("Content")
        if kind not in {"Text", "Html"} or not isinstance(content, str):
            raise ValueError(f"{field}: Type debe ser 'Text' o 'Html' y Content un string")
        return (content, None) if kind == "Text" else (_strip_tags(content), content)
    text, html = value.get("Text"), value.get("Html")
    if not isinstance(text, (str, type(None))) or not isinstance(html, (str, type(None))):
        raise ValueError(f"{field}: Text y Html deben ser strings")
    return text or (_strip_tags(html) if html else ""), html


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


# ───────────────────────── usuarios ─────────────────────────

def who_am_i(user: sqlite3.Row) -> dict:
    return {
        "Identifier": str(user["id"]),
        "FirstName": user["first_name"],
        "LastName": user["last_name"],
        "UniqueName": user["username"],
        "ProfileIdentifier": user["profile_identifier"],
        "Pronouns": "",
    }


def user_data(user: sqlite3.Row, org_id: int) -> dict:
    return {
        "OrgId": org_id,
        "UserId": user["id"],
        "FirstName": user["first_name"],
        "MiddleName": None,
        "LastName": user["last_name"],
        "UserName": user["username"],
        "ExternalEmail": user["email"],
        "OrgDefinedId": user["org_defined_id"],
        "UniqueIdentifier": user["username"],
        "Activation": {"IsActive": bool(user["is_active"])},
        "DisplayName": f"{user['first_name']} {user['last_name']}",
        "LastAccessedDate": user["last_accessed"] or user["created_at"],
        "Pronouns": "",
        "FirstLoginDate": user["last_accessed"],
    }


def user_composite(user: sqlite3.Row) -> dict:
    """User.User, usado dentro de OrgUnitUser y UserGradeValue [APROX: forma tomada de conocimiento previo]."""
    return {
        "Identifier": str(user["id"]),
        "DisplayName": f"{user['first_name']} {user['last_name']}",
        "EmailAddress": user["email"],
        "OrgDefinedId": user["org_defined_id"],
        "ProfileBadgeUrl": None,
        "ProfileIdentifier": user["profile_identifier"],
    }


def role_info(role: sqlite3.Row) -> dict:
    return {"Id": role["id"], "Code": role["code"], "Name": role["name"]}


# ───────────────────────── unidades organizacionales e inscripciones ─────────────────────────

def org_unit_info(ou: sqlite3.Row) -> dict:
    return {
        "Id": ou["id"],
        "Type": {"Id": ou["type_id"], "Code": ou["type_code"], "Name": ou["type_name"]},
        "Name": ou["name"],
        "Code": ou["code"],
        "HomeUrl": f"/d2l/home/{ou['id']}",  # [APROX]
        "ImageUrl": None,
    }


_LIS_ROLES = {  # [APROX] equivalencias típicas con los roles LIS
    "instructor": ["urn:lti:role:ims/lis/Instructor"],
    "student": ["urn:lti:role:ims/lis/Learner"],
}


def my_org_unit_info(row: sqlite3.Row) -> dict:
    return {
        "OrgUnit": org_unit_info(row),
        "Access": {
            "IsActive": bool(row["is_active"]),
            "StartDate": row["start_date"],
            "EndDate": row["end_date"],
            "CanAccess": bool(row["is_active"]),
            "ClasslistRoleName": row["role_name"],
            "LISRoles": _LIS_ROLES.get(row["role_kind"], []),
            "LastAccessed": None,
        },
        "PinDate": None,
    }


def classlist_user(user: sqlite3.Row, *, full: bool) -> dict:
    """ClasslistUser [DOC]. Si quien pregunta no tiene permiso, los campos privados van en null [APROX]."""
    return {
        "Identifier": str(user["id"]),
        "ProfileIdentifier": user["profile_identifier"],
        "DisplayName": f"{user['first_name']} {user['last_name']}",
        "Username": user["username"] if full else None,
        "OrgDefinedId": user["org_defined_id"] if full else None,
        "Email": user["email"] if full else None,
        "FirstName": user["first_name"],
        "LastName": user["last_name"],
        "RoleId": user["role_id"] if full else None,
        "LastAccessed": user["last_accessed"] if full else None,
        "IsOnline": False,
        "ClasslistRoleDisplayName": user["role_name"],
        "Pronouns": None,
    }


# ───────────────────────── paginación ─────────────────────────
# [APROX] Estructuras tomadas de conocimiento previo; no se pudieron verificar en la doc pública.

def paged_result_set(items: list, has_more: bool, bookmark: str | None) -> dict:
    return {"PagingInfo": {"Bookmark": bookmark or "", "HasMoreItems": has_more}, "Items": items}


def object_list_page(objects: list, next_url: str | None) -> dict:
    return {"Next": next_url, "Objects": objects}


def next_page_url(base_url: str, path: str, params: dict) -> str:
    clean = {k: v for k, v in params.items() if v is not None}
    return f"{base_url}{path}?{urlencode(clean)}"


# ───────────────────────── carpetas de entrega ─────────────────────────

def dropbox_folder(folder: sqlite3.Row, counts: dict | None) -> dict:
    """DropboxFolder [DOC]. counts=None cuando el usuario no puede ver totales: van en -1 [DOC]."""
    c = counts or {}
    has_dates = folder["start_date"] or folder["end_date"]
    return {
        "Id": folder["id"],
        "CategoryId": folder["category_id"],
        "Name": folder["name"],
        "CustomInstructions": rich_text(folder["instructions_text"], folder["instructions_html"]),
        "Attachments": [],
        "TotalFiles": c.get("files", -1),
        "UnreadFiles": c.get("unread", -1),
        "FlaggedFiles": c.get("flagged", -1),
        "TotalUsers": c.get("users", -1),
        "TotalUsersWithSubmissions": c.get("with_submissions", -1),
        "TotalUsersWithFeedback": c.get("with_feedback", -1),
        "Availability": {
            "StartDate": folder["start_date"],
            "EndDate": folder["end_date"],
            "StartDateAvailabilityType": None,
            "EndDateAvailabilityType": None,
        } if has_dates else None,
        "GroupTypeId": None,
        "DueDate": folder["due_date"],
        "DisplayInCalendar": bool(folder["display_in_calendar"]),
        "Assessment": {"ScoreDenominator": folder["score_denominator"], "Rubrics": []}
        if folder["score_denominator"] is not None else None,
        "NotificationEmail": folder["notification_email"],
        "IsHidden": bool(folder["is_hidden"]),
        "LinkAttachments": [],
        "ActivityId": None,  # [APROX]
        "IsAnonymous": bool(folder["is_anonymous"]),
        "DropboxType": folder["dropbox_type"],
        "SubmissionType": folder["submission_type"],
        "CompletionType": folder["completion_type"],
        "SubmissionRule": folder["submission_rule"],
        "GradeItemId": folder["grade_item_id"],
        "AllowOnlyUsersWithSpecialAccess": bool(folder["allow_special_access"]),
    }


def feedback_out(row: sqlite3.Row) -> dict:
    """DropboxFeedbackOut [DOC]: DropboxFeedback + Files + Links (el mock no maneja adjuntos)."""
    return {
        "Score": row["score"],
        "Feedback": rich_text(row["feedback_text"], row["feedback_html"]),
        "RubricAssessments": [],
        "IsGraded": bool(row["is_graded"]),
        "GradedSymbol": None,
        "Files": [],
        "Links": [],
    }


# Estados de EntityDropbox [DOC]: Unsubmitted 0, Submitted 1, Draft 2, Published 3.
UNSUBMITTED, SUBMITTED, DRAFT, PUBLISHED = 0, 1, 2, 3


def entity_dropbox(user: sqlite3.Row, submissions: list[dict], feedback: sqlite3.Row | None,
                   *, show_draft_feedback: bool) -> dict:
    if feedback is not None and feedback["is_graded"]:
        status, fb = PUBLISHED, feedback_out(feedback)
    elif feedback is not None and show_draft_feedback:
        status, fb = DRAFT, feedback_out(feedback)
    else:
        status, fb = (SUBMITTED if submissions else UNSUBMITTED), None
    return {
        "Entity": {"EntityId": user["id"], "EntityType": "User",
                   "DisplayName": f"{user['first_name']} {user['last_name']}"},
        "Status": status,
        "Feedback": fb,
        "Submissions": submissions,
        "CompletionDate": None,
    }


def submission(sub: sqlite3.Row, files: list[sqlite3.Row]) -> dict:
    return {
        "Id": sub["id"],
        "SubmittedBy": {"Id": str(sub["user_id"]), "DisplayName": sub["display_name"]},
        "SubmissionDate": sub["submitted_at"],
        "Comment": rich_text(sub["comment_text"], sub["comment_html"]),
        "Files": [
            {"FileId": f["id"], "FileName": f["file_name"], "Size": f["size"],
             "isRead": bool(f["is_read"]), "isFlagged": bool(f["is_flagged"])}
            for f in files
        ],
    }


# ───────────────────────── calificaciones ─────────────────────────

def grade_object(go: sqlite3.Row, version: str, *, associated_folder_id: int | None) -> dict:
    return {
        "MaxPoints": go["max_points"],
        "CanExceedMaxPoints": bool(go["can_exceed"]),
        "IsBonus": bool(go["is_bonus"]),
        "ExcludeFromFinalGradeCalculation": bool(go["exclude_from_final"]),
        "GradeSchemeId": None,
        "Id": go["id"],
        "Name": go["name"],
        "ShortName": go["short_name"],
        "GradeType": "Numeric",
        "CategoryId": None,
        "Description": rich_text(go["description"], None),
        "GradeSchemeUrl": f"/d2l/api/le/{version}/{go['org_unit_id']}/grades/schemes/0",  # [APROX]
        "Weight": 0,
        "AssociatedTool": {"ToolId": 2000, "ToolItemId": associated_folder_id}  # [APROX] ids de herramienta
        if associated_folder_id else None,
        "IsHidden": bool(go["is_hidden"]),
    }


def _fmt_points(value: float) -> str:
    return f"{value:g}"


def grade_value(gv: sqlite3.Row, go: sqlite3.Row, *, include_private: bool) -> dict:
    """GradeValue numérico [DOC] (campos básicos + 'computable')."""
    return {
        "DisplayedGrade": f"{_fmt_points(gv['points'])} / {_fmt_points(go['max_points'])}",  # [APROX] formato
        "GradeObjectIdentifier": str(go["id"]),
        "GradeObjectName": go["name"],
        "GradeObjectType": 1,
        "GradeObjectTypeName": "Numeric",
        "Comments": rich_text(gv["comments_text"], gv["comments_html"]),
        "PrivateComments": rich_text(gv["private_text"], gv["private_html"]) if include_private else rich_text("", None),
        "LastModified": gv["last_modified"],
        "LastModifiedBy": gv["last_modified_by"],
        "ReleasedDate": gv["released_date"],
        "PointsNumerator": gv["points"],
        "PointsDenominator": go["max_points"],
        "WeightedNumerator": None,
        "WeightedDenominator": None,
    }


def final_grade_value(points: float, max_points: float, last_modified: str | None) -> dict:
    """Nota final calculada [APROX: suma de puntos / suma de máximos de los ítems con nota]."""
    return {
        "DisplayedGrade": f"{_fmt_points(points)} / {_fmt_points(max_points)}",
        "GradeObjectIdentifier": "0",
        "GradeObjectName": "Final Calculated Grade",
        "GradeObjectType": 7,
        "GradeObjectTypeName": "Final Calculated",
        "Comments": rich_text("", None),
        "PrivateComments": rich_text("", None),
        "LastModified": last_modified,
        "LastModifiedBy": None,
        "ReleasedDate": last_modified,
        "PointsNumerator": points,
        "PointsDenominator": max_points,
        "WeightedNumerator": None,
        "WeightedDenominator": None,
    }


def is_open(folder: sqlite3.Row, now) -> bool:
    """¿La carpeta acepta entregas en este momento? (entre StartDate y EndDate, si existen)."""
    start, end = parse_d2l_date(folder["start_date"]), parse_d2l_date(folder["end_date"])
    return (start is None or start <= now) and (end is None or now <= end)

