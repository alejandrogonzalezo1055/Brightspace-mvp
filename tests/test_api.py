"""Rutas de la API estilo Valence: autenticación, scopes, roles, entregas, retroalimentación y notas."""
from app.main import create_app

INSTRUCTOR, OTHER_INSTRUCTOR, STUDENT, STUDENT2, OTHER_STUDENT = 3001, 3002, 3101, 3102, 3104
LE, LP = "/d2l/api/le/1.82", "/d2l/api/lp/1.49"
FOLDERS = f"{LE}/6650/dropbox/folders"
BOUNDARY = "xxBOUNDARYxx"


def multipart(comment: str = "mi entrega", files=(("main.cpp", "text/x-c++src", b"int main(){}"),),
              json_part: bytes | None = None) -> tuple[dict, bytes]:
    parts = [f"--{BOUNDARY}\r\nContent-Type: application/json\r\n\r\n".encode()
             + (json_part if json_part is not None else f'{{"Text": "{comment}", "Html": null}}'.encode()) + b"\r\n"]
    for name, ctype, data in files:
        parts.append(f'--{BOUNDARY}\r\nContent-Disposition: form-data; name=""; filename="{name}"\r\n'
                     f"Content-Type: {ctype}\r\n\r\n".encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{BOUNDARY}--\r\n".encode()
    return {"Content-Type": f"multipart/mixed; boundary={BOUNDARY}"}, body


# ───────────────────────── autenticación, scopes y versiones ─────────────────────────

def test_missing_bad_or_expired_token_is_403_invalid_token(client, token_for):
    assert (r := client.get(f"{LP}/users/whoami")).status_code == 403 and r.text == "Invalid Token"
    assert client.get(f"{LP}/users/whoami", headers={"Authorization": "Bearer basura"}).text == "Invalid Token"
    assert client.get(f"{LP}/users/whoami", headers=token_for(STUDENT, lifetime=-10)).text == "Invalid Token"


def test_authentication_header_variant_is_accepted(client, token_for):
    token = token_for(STUDENT)["Authorization"]
    assert client.get(f"{LP}/users/whoami", headers={"Authentication": token}).status_code == 200


def test_missing_scope_is_403(client, token_for):
    headers = token_for(STUDENT, scope="enrollment:own_enrollment:read")
    response = client.get(f"{LP}/users/whoami", headers=headers)
    assert response.status_code == 403 and "Insufficient scope" in response.text


def test_wildcard_and_comma_scopes(client, token_for):
    assert client.get(f"{FOLDERS}/", headers=token_for(STUDENT, scope="dropbox:*:read")).status_code == 200
    assert client.get(f"{FOLDERS}/", headers=token_for(STUDENT, scope="dropbox:folders:write,read")).status_code == 200
    # core:*:* NO alcanza para rutas con scope específico en modo estricto (por defecto).
    assert client.get(f"{FOLDERS}/", headers=token_for(STUDENT, scope="core:*:*")).status_code == 403


def test_unsupported_version_and_trailing_slash_are_404(client, token_for):
    headers = token_for(STUDENT)
    assert client.get("/d2l/api/lp/1.20/users/whoami", headers=headers).status_code == 404
    assert client.get(FOLDERS, headers=headers).status_code == 404  # sin barra final
    assert client.get(f"{LE}/abc/dropbox/folders/", headers=headers).status_code == 404


def test_versions_routes_are_anonymous(client):
    all_versions = client.get("/d2l/api/versions/").json()
    assert {v["ProductCode"] for v in all_versions} == {"lp", "le"}
    assert client.get("/d2l/api/lp/versions/1.49").json() == {"Supported": True, "LatestVersion": "1.49"}
    bulk = client.post("/d2l/api/versions/check", json=[{"ProductCode": "le", "Version": "1.82"},
                                                         {"ProductCode": "lp", "Version": "9.99"}]).json()
    assert bulk["Supported"] is False and len(bulk["Versions"]) == 2


def test_rate_limit_headers_and_429(settings, token_for):
    from fastapi.testclient import TestClient
    settings.rate_limit_capacity = 3
    settings.rate_limit_window_s = 3600
    small = TestClient(create_app(settings), base_url="http://testserver")
    headers = {"Authorization": token_for(STUDENT)["Authorization"]}
    first = small.get(f"{LP}/users/whoami", headers=headers)
    assert first.headers["X-Rate-Limit-Remaining"] == "2" and first.headers["X-Request-Cost"] == "1"
    small.get(f"{LP}/users/whoami", headers=headers)
    small.get(f"{LP}/users/whoami", headers=headers)
    blocked = small.get(f"{LP}/users/whoami", headers=headers)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0


# ───────────────────────── usuarios e inscripciones ─────────────────────────

def test_myenrollments_is_a_paged_result_set(client, token_for):
    body = client.get(f"{LP}/enrollments/myenrollments/", headers=token_for(STUDENT)).json()
    assert set(body) == {"PagingInfo", "Items"} and body["PagingInfo"]["HasMoreItems"] is False
    course = body["Items"][0]
    assert course["OrgUnit"]["Id"] == 6650 and course["OrgUnit"]["Type"]["Code"] == "Course Offering"
    assert course["Access"]["ClasslistRoleName"] == "Student"


def test_myenrollments_paging_with_bookmark(settings, token_for):
    from fastapi.testclient import TestClient
    settings.page_size = 1
    small = TestClient(create_app(settings), base_url="http://testserver")
    from app.db import transaction
    with transaction(settings.db_path) as conn:
        conn.execute("INSERT INTO enrollments (user_id, org_unit_id, role_id) VALUES (3101, 6651, 110)")
    page1 = small.get(f"{LP}/enrollments/myenrollments/", headers=token_for(STUDENT)).json()
    assert page1["PagingInfo"]["HasMoreItems"] is True
    page2 = small.get(f"{LP}/enrollments/myenrollments/", headers=token_for(STUDENT),
                      params={"bookmark": page1["PagingInfo"]["Bookmark"]}).json()
    assert [i["OrgUnit"]["Id"] for i in page1["Items"] + page2["Items"]] == [6650, 6651]


def test_users_visibility(client, token_for):
    assert client.get(f"{LP}/users/{STUDENT}", headers=token_for(INSTRUCTOR)).status_code == 200
    assert client.get(f"{LP}/users/{STUDENT}", headers=token_for(OTHER_INSTRUCTOR)).status_code == 403
    assert client.get(f"{LP}/users/{STUDENT2}", headers=token_for(STUDENT)).status_code == 403
    assert client.get(f"{LP}/users/{STUDENT}", headers=token_for(STUDENT)).json()["UserName"] == "estudiante1"


def test_classlist_hides_private_fields_from_students(client, token_for):
    as_student = client.get(f"{LE}/6650/classlist/", headers=token_for(STUDENT)).json()
    as_teacher = client.get(f"{LE}/6650/classlist/", headers=token_for(INSTRUCTOR)).json()
    assert all(u["Email"] is None for u in as_student)
    assert any(u["Email"] for u in as_teacher)
    paged = client.get(f"{LE}/6650/classlist/paged/", headers=token_for(INSTRUCTOR), params={"roleId": 110}).json()
    assert set(paged) == {"Next", "Objects"} and len(paged["Objects"]) == 3


def test_other_course_is_forbidden(client, token_for):
    assert client.get(f"{FOLDERS}/", headers=token_for(OTHER_INSTRUCTOR)).status_code == 403
    assert client.get(f"{FOLDERS}/", headers=token_for(OTHER_STUDENT)).status_code == 403
    assert client.get(f"{LE}/9999/dropbox/folders/", headers=token_for(INSTRUCTOR)).status_code == 404


# ───────────────────────── carpetas y entregas ─────────────────────────

def test_students_do_not_see_hidden_folders_or_counts(client, token_for):
    student_view = client.get(f"{FOLDERS}/", headers=token_for(STUDENT)).json()
    assert 703 not in {f["Id"] for f in student_view}
    assert all(f["TotalUsers"] == -1 for f in student_view)
    assert client.get(f"{FOLDERS}/703", headers=token_for(STUDENT)).status_code == 404
    teacher_view = client.get(f"{FOLDERS}/701", headers=token_for(INSTRUCTOR)).json()
    assert teacher_view["TotalUsers"] == 3 and teacher_view["TotalUsersWithSubmissions"] == 1
    assert teacher_view["GradeItemId"] == 5001 and teacher_view["Assessment"]["ScoreDenominator"] == 100.0


def test_student_submits_with_multipart_mixed(client, token_for):
    headers, body = multipart("versión final", files=[("main.cpp", "text/x-c++src", b"// codigo"),
                                                       ("notas.txt", "text/plain", b"hola")])
    url = f"{FOLDERS}/702/submissions/mysubmissions/"
    response = client.post(url, headers={**token_for(STUDENT2), **headers}, content=body)
    assert response.status_code == 200 and response.content == b""
    mine = client.get(url, headers=token_for(STUDENT2)).json()[0]
    assert mine["Status"] == 1 and mine["Feedback"] is None
    submission = mine["Submissions"][0]
    assert submission["Comment"]["Text"] == "versión final"
    assert [f["FileName"] for f in submission["Files"]] == ["main.cpp", "notas.txt"]

    file_id = submission["Files"][0]["FileId"]
    download = client.get(f"{FOLDERS}/702/submissions/{submission['Id']}/files/{file_id}", headers=token_for(INSTRUCTOR))
    assert download.status_code == 200 and download.content == b"// codigo"
    # Otro estudiante no puede descargar el archivo ajeno.
    assert client.get(f"{FOLDERS}/702/submissions/{submission['Id']}/files/{file_id}",
                      headers=token_for(STUDENT)).status_code == 404


def test_submission_errors(client, token_for):
    url = f"{FOLDERS}/701/submissions/mysubmissions/"
    headers, body = multipart()
    assert client.post(url, headers={**token_for(INSTRUCTOR), **headers}, content=body).status_code == 403
    assert client.post(f"{FOLDERS}/704/submissions/mysubmissions/", headers={**token_for(STUDENT), **headers},
                       content=body).status_code == 403  # carpeta cerrada
    assert client.post(url, headers=token_for(STUDENT), json={"Text": "x"}).status_code == 415
    no_file_headers, no_file = multipart(files=())
    assert client.post(url, headers={**token_for(STUDENT), **no_file_headers}, content=no_file).status_code == 400
    bad_json_headers, bad_json = multipart(json_part=b"{no es json")
    assert client.post(url, headers={**token_for(STUDENT), **bad_json_headers}, content=bad_json).status_code == 400


def test_instructor_lists_submissions_paged(client, token_for):
    paged = client.get(f"{FOLDERS}/701/submissions/paged/", headers=token_for(INSTRUCTOR)).json()
    assert paged["Next"] is None and len(paged["Objects"]) == 3
    statuses = {o["Entity"]["EntityId"]: o["Status"] for o in paged["Objects"]}
    assert statuses == {3101: 1, 3102: 0, 3103: 0}
    assert client.get(f"{FOLDERS}/701/submissions/", headers=token_for(STUDENT)).status_code == 403


def test_create_and_update_folder(client, token_for):
    new = {"Name": "Taller 4", "CustomInstructions": {"Content": "<p>Sube <b>main.cpp</b></p>", "Type": "Html"},
           "Availability": {"StartDate": "2026-01-01T00:00:00.000Z", "EndDate": "2030-01-01T00:00:00.000Z"},
           "DueDate": "2029-12-31T23:59:00.000Z", "IsHidden": False, "Assessment": {"ScoreDenominator": 10},
           "DropboxType": 2, "SubmissionType": 0, "CompletionType": 0, "GradeItemId": 5002}
    created = client.post(f"{FOLDERS}/", headers=token_for(INSTRUCTOR), json=new)
    assert created.status_code == 200, created.text
    folder = created.json()
    assert folder["CustomInstructions"] == {"Text": "Sube main.cpp", "Html": "<p>Sube <b>main.cpp</b></p>"}

    updated = client.put(f"{FOLDERS}/{folder['Id']}", headers=token_for(INSTRUCTOR), json={"Name": "Taller 4 (v2)"})
    assert updated.json()["Name"] == "Taller 4 (v2)" and updated.json()["DueDate"] == "2029-12-31T23:59:00.000Z"

    bad_date = {**new, "DueDate": "2029-12-31"}
    assert client.post(f"{FOLDERS}/", headers=token_for(INSTRUCTOR), json=bad_date).status_code == 400
    assert client.post(f"{FOLDERS}/", headers=token_for(STUDENT), json=new).status_code == 403
    assert client.post(f"{FOLDERS}/", headers=token_for(INSTRUCTOR), content=b"Name=x",
                       ).status_code == 415


# ───────────────────────── retroalimentación y notas ─────────────────────────

def test_feedback_draft_then_publish_updates_gradebook(client, token_for):
    url = f"{FOLDERS}/701/feedback/user/{STUDENT}"
    draft = {"Score": 80, "Feedback": {"Text": "Buen manejo de condicionales.", "Html": None}, "IsGraded": False}
    assert client.post(url, headers=token_for(INSTRUCTOR), json=draft).status_code == 200
    # El borrador lo ve el docente pero no el estudiante.
    assert client.get(url, headers=token_for(INSTRUCTOR)).json()["IsGraded"] is False
    assert client.get(url, headers=token_for(STUDENT)).status_code == 404
    assert client.get(f"{LE}/6650/grades/5001/values/myGradeValue", headers=token_for(STUDENT)).status_code == 404

    published = {**draft, "IsGraded": True}
    assert client.post(url, headers=token_for(INSTRUCTOR), json=published).status_code == 200
    assert client.get(url, headers=token_for(STUDENT)).json()["Score"] == 80
    mine = client.get(f"{FOLDERS}/701/submissions/mysubmissions/", headers=token_for(STUDENT)).json()[0]
    assert mine["Status"] == 3

    grade = client.get(f"{LE}/6650/grades/5001/values/myGradeValue", headers=token_for(STUDENT)).json()
    assert grade["PointsNumerator"] == 4.0 and grade["PointsDenominator"] == 5.0  # 80/100 de 5 puntos
    final = client.get(f"{LE}/6650/grades/final/values/myGradeValue", headers=token_for(STUDENT)).json()
    assert final["PointsNumerator"] == 4.0 and final["GradeObjectType"] == 7


def test_feedback_validation(client, token_for):
    url = f"{FOLDERS}/701/feedback/user/{STUDENT}"
    assert client.post(url, headers=token_for(STUDENT), json={"Score": 1}).status_code == 403
    assert client.post(url, headers=token_for(INSTRUCTOR), json={"Score": "diez"}).status_code == 400
    assert client.post(f"{FOLDERS}/701/feedback/user/{OTHER_STUDENT}", headers=token_for(INSTRUCTOR),
                       json={"Score": 1}).status_code == 404
    assert client.post(f"{FOLDERS}/701/feedback/group/1", headers=token_for(INSTRUCTOR),
                       json={"Score": 1}).status_code == 404


def test_grade_values(client, token_for):
    url = f"{LE}/6650/grades/5002/values/{STUDENT2}"
    incoming = {"GradeObjectType": 1, "PointsNumerator": 4.5,
                "Comments": {"Content": "Bien", "Type": "Text"}, "PrivateComments": {"Content": "ok", "Type": "Text"}}
    assert client.put(url, headers=token_for(INSTRUCTOR), json=incoming).status_code == 200
    assert client.put(url, headers=token_for(INSTRUCTOR), json={**incoming, "PointsNumerator": 9}).status_code == 400
    assert client.put(url, headers=token_for(INSTRUCTOR), json={**incoming, "GradeObjectType": 2}).status_code == 400
    assert client.put(url, headers=token_for(STUDENT2), json=incoming).status_code == 403

    teacher_view = client.get(url, headers=token_for(INSTRUCTOR)).json()
    assert teacher_view["PrivateComments"]["Text"] == "ok"
    student_view = client.get(f"{LE}/6650/grades/5002/values/myGradeValue", headers=token_for(STUDENT2)).json()
    assert student_view["PointsNumerator"] == 4.5 and student_view["PrivateComments"]["Text"] == ""

    listing = client.get(f"{LE}/6650/grades/5002/values/", headers=token_for(INSTRUCTOR)).json()
    graded = [o for o in listing["Objects"] if o["GradeValue"]]
    assert len(listing["Objects"]) == 3 and len(graded) == 1
    only_graded = client.get(f"{LE}/6650/grades/5002/values/", headers=token_for(INSTRUCTOR),
                             params={"isGraded": "true"}).json()
    assert len(only_graded["Objects"]) == 1

    objects = client.get(f"{LE}/6650/grades/", headers=token_for(STUDENT)).json()
    assert {o["Id"] for o in objects} == {5001, 5002}
    assert client.get(f"{LE}/6650/grades/values/myGradeValues/", headers=token_for(STUDENT2)).json()[0]["GradeObjectIdentifier"] == "5002"
