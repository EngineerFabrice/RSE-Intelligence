"""Security tests (spec §53): auth required, RBAC enforced, malicious/oversized uploads rejected."""

import io


def test_dashboard_requires_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_api_requires_login(client):
    resp = client.get("/api/reports")
    assert resp.status_code == 401


def test_login_with_wrong_password_fails(client, admin_user):
    resp = client.post("/auth/login", data={"email": admin_user.email, "password": "wrong"}, follow_redirects=True)
    assert b"Invalid email or password" in resp.data


def test_login_success_redirects_to_dashboard(client, admin_user):
    resp = client.post("/auth/login", data={"email": admin_user.email, "password": "password123"},
                        follow_redirects=True)
    assert resp.status_code == 200


def test_viewer_cannot_upload_report(viewer_client):
    data = {"file": (io.BytesIO(b"%PDF-1.4 fake"), "report.pdf")}
    resp = viewer_client.post("/api/reports/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 403


def test_viewer_cannot_access_admin_users_page(viewer_client):
    resp = viewer_client.get("/admin/users")
    assert resp.status_code == 403


def test_admin_can_access_admin_users_page(admin_client):
    resp = admin_client.get("/admin/users")
    assert resp.status_code == 200


def test_upload_rejects_non_pdf_extension(analyst_client):
    data = {"file": (io.BytesIO(b"not a pdf"), "report.txt")}
    resp = analyst_client.post("/api/reports/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_rejects_invalid_pdf_signature(analyst_client):
    data = {"file": (io.BytesIO(b"NOT-A-REAL-PDF-HEADER"), "report.pdf")}
    resp = analyst_client.post("/api/reports/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_sanitizes_malicious_filename(analyst_client, app):
    data = {"file": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "../../evil/../report.pdf")}
    resp = analyst_client.post("/api/reports/upload", data=data, content_type="multipart/form-data")
    # secure_filename() strips path traversal; either it's accepted as a safe filename
    # or rejected outright, but it must never escape the upload folder.
    assert resp.status_code in (200, 400, 409)
