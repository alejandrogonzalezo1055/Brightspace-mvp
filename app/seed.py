"""
Datos de demostración. Se cargan solos la primera vez que arranca el mock (base vacía).

Los IDs, roles y tipos de unidad son inventados [APROX]: el cliente de EduTrace nunca debe
tenerlos fijos en el código; debe descubrirlos con la API (whoami, myenrollments, etc.).
"""
import os
import secrets
from datetime import timedelta

from app.config import Settings
from app.db import now_str, to_d2l_date, transaction, utc_now
from app.security.passwords import hash_password

ROLE_INSTRUCTOR, ROLE_STUDENT, ROLE_ADMIN, ROLE_SERVICE, ROLE_USER = 109, 110, 111, 112, 113
ORG_ID, COURSE_IP, COURSE_ED = 6606, 6650, 6651


def demo_password() -> str:
    return os.getenv("MOCK_DEMO_PASSWORD", "Mock2026!")


def seed_demo_if_empty(settings: Settings) -> bool:
    with transaction(settings.db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return False
        _seed(conn, settings)
    return True


def _seed(conn, settings: Settings) -> None:
    now = utc_now()
    created = now_str()
    password = hash_password(demo_password())

    conn.executemany("INSERT INTO org_unit_types (id, code, name) VALUES (?, ?, ?)",
                     [(1, "Organization", "Organization"), (3, "Course Offering", "Course Offering")])
    conn.executemany("INSERT INTO roles (id, code, name, kind) VALUES (?, ?, ?, ?)", [
        (ROLE_INSTRUCTOR, "Instructor", "Instructor", "instructor"),
        (ROLE_STUDENT, "Student", "Student", "student"),
        (ROLE_ADMIN, "Administrator", "Administrator", "admin"),
        (ROLE_SERVICE, "ServiceUser", "Service User", "service"),
        (ROLE_USER, "User", "User", "user"),
    ])

    course_start, course_end = to_d2l_date(now - timedelta(days=60)), to_d2l_date(now + timedelta(days=60))
    conn.executemany(
        "INSERT INTO org_units (id, type_id, name, code, is_active, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (ORG_ID, 1, "Universidad Simulada", "UNI", 1, None, None),
            (COURSE_IP, 3, "Introducción a la Programación (2026-2)", "IP-2026-2", 1, course_start, course_end),
            (COURSE_ED, 3, "Estructuras de Datos (2026-2)", "ED-2026-2", 1, course_start, course_end),
        ])

    users = [
        # id, username, nombre, apellido, correo, código institucional, rol en la organización, ¿tiene contraseña?
        (3001, "docente1", "Ana", "Rojas", "ana.rojas@uni.example", "D-1001", ROLE_USER, True),
        (3002, "docente2", "Luis", "Pardo", "luis.pardo@uni.example", "D-1002", ROLE_USER, True),
        (3101, "estudiante1", "Camila", "Díaz", "camila.diaz@uni.example", "20261001", ROLE_USER, True),
        (3102, "estudiante2", "Mateo", "Gómez", "mateo.gomez@uni.example", "20261002", ROLE_USER, True),
        (3103, "estudiante3", "Valentina", "Ruiz", "valentina.ruiz@uni.example", "20261003", ROLE_USER, True),
        (3104, "estudiante4", "Samuel", "Torres", "samuel.torres@uni.example", "20261004", ROLE_USER, True),
        (3900, "admin", "Admin", "Mock", "admin@uni.example", None, ROLE_ADMIN, True),
        (3950, "svc_edutrace", "Servicio", "EduTrace", None, None, ROLE_SERVICE, False),
    ]
    for uid, username, first, last, email, org_id, role, has_password in users:
        conn.execute(
            """INSERT INTO users (id, username, first_name, last_name, email, org_defined_id, profile_identifier,
                                  password_hash, is_active, org_role_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (uid, username, first, last, email, org_id, secrets.token_urlsafe(8),
             password if has_password else None, role, created))

    conn.executemany("INSERT INTO enrollments (user_id, org_unit_id, role_id) VALUES (?, ?, ?)", [
        (3001, COURSE_IP, ROLE_INSTRUCTOR),
        (3101, COURSE_IP, ROLE_STUDENT), (3102, COURSE_IP, ROLE_STUDENT), (3103, COURSE_IP, ROLE_STUDENT),
        (3002, COURSE_ED, ROLE_INSTRUCTOR), (3104, COURSE_ED, ROLE_STUDENT),
    ])

    conn.executemany(
        "INSERT INTO grade_objects (id, org_unit_id, name, short_name, max_points, description) VALUES (?, ?, ?, ?, ?, ?)", [
            (5001, COURSE_IP, "Taller 1: Condicionales", "T1", 5.0, "Nota del taller 1"),
            (5002, COURSE_IP, "Taller 2: Ciclos", "T2", 5.0, "Nota del taller 2"),
            (5101, COURSE_ED, "Taller 1: Listas enlazadas", "T1", 5.0, ""),
        ])

    start, due, end = (to_d2l_date(now - timedelta(days=7)), to_d2l_date(now + timedelta(days=14)),
                       to_d2l_date(now + timedelta(days=21)))
    folders = [
        # id, curso, nombre, instrucciones, inicio, entrega, cierre, oculta, denominador, ítem de nota
        (701, COURSE_IP, "Taller 1: Condicionales", "Sube tu archivo main.cpp.", start, due, end, 0, 100.0, 5001),
        (702, COURSE_IP, "Taller 2: Ciclos", "Sube tu archivo main.cpp.", start, due, end, 0, 100.0, 5002),
        (703, COURSE_IP, "Taller 3 (borrador oculto)", "Aún no publicado.", start, due, end, 1, 100.0, None),
        (704, COURSE_IP, "Taller 0 (cerrado)", "Ya cerró.", to_d2l_date(now - timedelta(days=30)),
         to_d2l_date(now - timedelta(days=20)), to_d2l_date(now - timedelta(days=15)), 0, 100.0, None),
        (751, COURSE_ED, "Taller 1: Listas enlazadas", "Sube tu código.", start, due, end, 0, 100.0, 5101),
    ]
    for fid, ou, name, text, s, d, e, hidden, denom, grade_item in folders:
        conn.execute(
            """INSERT INTO dropbox_folders (id, org_unit_id, name, instructions_text, start_date, due_date, end_date,
                                            is_hidden, score_denominator, grade_item_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (fid, ou, name, text, s, d, e, hidden, denom, grade_item))

    # Una entrega de ejemplo de estudiante1 en el Taller 1.
    cursor = conn.execute(
        "INSERT INTO submissions (folder_id, user_id, submitted_at, comment_text) VALUES (701, 3101, ?, ?)",
        (now_str(), "Primera versión del taller."))
    code = b'#include <iostream>\nint main() {\n    int n; std::cin >> n;\n    std::cout << (n % 2 == 0 ? "par" : "impar") << std::endl;\n}\n'
    file_cursor = conn.execute(
        "INSERT INTO submission_files (submission_id, file_name, content_type, size, storage_path) VALUES (?, 'main.cpp', 'text/x-c++src', ?, '')",
        (cursor.lastrowid, len(code)))
    relative = f"{cursor.lastrowid}/{file_cursor.lastrowid}"
    (settings.uploads_dir / str(cursor.lastrowid)).mkdir(parents=True, exist_ok=True)
    (settings.uploads_dir / relative).write_bytes(code)
    conn.execute("UPDATE submission_files SET storage_path = ? WHERE id = ?", (relative, file_cursor.lastrowid))
