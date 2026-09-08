import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture
def app(tmp_path):
    application = create_app("testing")
    application.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    os.makedirs(application.config["UPLOAD_FOLDER"], exist_ok=True)
    # A file-backed SQLite DB (rather than :memory:) so every connection checked out of
    # the pool during a test sees the same tables/data.
    application.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'test.db'}"

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()

    shutil.rmtree(application.config["UPLOAD_FOLDER"], ignore_errors=True)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(db, role, email):
    user = User(name=role.title(), email=email, role=role, status="active")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(db):
    # NOTE: the ".test" TLD is an IANA reserved special-use domain that the
    # email_validator library used by WTForms explicitly rejects, so test fixtures use a
    # syntactically valid but non-reserved domain instead.
    return _make_user(db, "administrator", "admin@rse-intelligence-qa.io")


@pytest.fixture
def analyst_user(db):
    return _make_user(db, "analyst", "analyst@rse-intelligence-qa.io")


@pytest.fixture
def viewer_user(db):
    return _make_user(db, "viewer", "viewer@rse-intelligence-qa.io")


@pytest.fixture
def reviewer_user(db):
    return _make_user(db, "reviewer", "reviewer@rse-intelligence-qa.io")


def login(client, email, password="password123"):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)


@pytest.fixture
def admin_client(client, admin_user):
    login(client, admin_user.email)
    return client


@pytest.fixture
def analyst_client(client, analyst_user):
    login(client, analyst_user.email)
    return client


@pytest.fixture
def viewer_client(client, viewer_user):
    login(client, viewer_user.email)
    return client


@pytest.fixture
def reviewer_client(client, reviewer_user):
    login(client, reviewer_user.email)
    return client
