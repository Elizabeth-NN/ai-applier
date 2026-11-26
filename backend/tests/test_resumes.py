from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_user
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app
from app.models.resume import Resume
import app.api.resumes as resumes_api


@pytest.fixture
def resume_context(tmp_path, monkeypatch) -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    storage = tmp_path / "private_uploads"
    monkeypatch.setattr(resumes_api, "STORAGE_DIR", storage)
    current_user = {"id": "user_test_1"}

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_user] = lambda: current_user["id"]

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "factory": factory,
                "user": current_user,
                "storage": storage,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def make_docx() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr("word/document.xml", "<document>Test resume</document>")
    return buffer.getvalue()


def upload(client, filename: str, content: bytes):
    return client.post(
        "/api/resumes",
        files={"file": (filename, content, "application/octet-stream")},
    )


def test_upload_and_list_pdf(resume_context):
    client = resume_context["client"]
    response = upload(client, "resume.pdf", b"%PDF-1.7\nexample")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "resume.pdf"
    assert body["size_bytes"] == len(b"%PDF-1.7\nexample")
    assert "storage_key" not in body

    listing = client.get("/api/resumes")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["id"] == body["id"]


def test_upload_valid_docx(resume_context):
    response = upload(resume_context["client"], "resume.docx", make_docx())
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("resume.txt", b"plain text"),
        ("resume.pdf", b"not a PDF"),
        ("resume.docx", b"PK\\x03\\x04not a real Word document"),
        ("resume.docx", b""),
    ],
)
def test_reject_invalid_uploads(resume_context, filename, content):
    response = upload(resume_context["client"], filename, content)
    assert response.status_code == 400


def test_reject_upload_larger_than_five_mib(resume_context):
    content = b"%PDF-" + b"x" * (5 * 1024 * 1024)
    response = upload(resume_context["client"], "large.pdf", content)
    assert response.status_code == 413


def test_download_returns_uploaded_content(resume_context):
    content = b"%PDF-1.7\nexample"
    created = upload(resume_context["client"], "my resume.pdf", content)
    assert created.status_code == 201
    resume_id = created.json()["id"]

    response = resume_context["client"].get(
        f"/api/resumes/{resume_id}/download"
    )
    assert response.status_code == 200
    assert response.content == content
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_user_cannot_list_or_download_another_users_resume(resume_context):
    client = resume_context["client"]
    created = upload(client, "private.pdf", b"%PDF-1.7\nprivate")
    assert created.status_code == 201
    resume_id = created.json()["id"]

    resume_context["user"]["id"] = "different_user"

    assert client.get("/api/resumes").json() == []
    assert client.get(f"/api/resumes/{resume_id}/download").status_code == 404
    assert client.delete(f"/api/resumes/{resume_id}").status_code == 404

    with resume_context["factory"]() as db:
        record = db.get(Resume, resume_id)
        assert record is not None
        assert record.user_id == "user_test_1"


def test_delete_removes_record_and_file(resume_context):
    client = resume_context["client"]
    created = upload(client, "remove.pdf", b"%PDF-1.7\nremove")
    assert created.status_code == 201
    resume_id = created.json()["id"]

    with resume_context["factory"]() as db:
        record = db.get(Resume, resume_id)
        stored_path = resume_context["storage"] / record.storage_key
        assert stored_path.is_file()

    response = client.delete(f"/api/resumes/{resume_id}")
    assert response.status_code == 204
    assert not stored_path.exists()
    assert client.get("/api/resumes").json() == []


def test_delete_storage_failure_preserves_resume_record_and_file(
    resume_context, monkeypatch
):
    client = resume_context["client"]
    created = upload(client, "keep.pdf", b"%PDF-1.7\nkeep")
    assert created.status_code == 201
    resume_id = created.json()["id"]

    with resume_context["factory"]() as db:
        record = db.get(Resume, resume_id)
        storage_key = record.storage_key

    stored_path = resume_context["storage"] / storage_key

    def fail_delete(*args, **kwargs):
        raise OSError("Simulated storage outage")

    monkeypatch.setattr(resumes_api.resume_storage, "delete_resume", fail_delete)

    response = client.delete(f"/api/resumes/{resume_id}")

    assert response.status_code == 500
    assert stored_path.is_file()

    with resume_context["factory"]() as db:
        assert db.get(Resume, resume_id) is not None

    assert len(client.get("/api/resumes").json()) == 1


def test_delete_database_commit_failure_restores_file_and_keeps_record(
    resume_context, monkeypatch
):
    client = resume_context["client"]
    content = b"%PDF-1.7\\nrestore"
    created = upload(client, "restore.pdf", content)
    assert created.status_code == 201
    resume_id = created.json()["id"]

    with resume_context["factory"]() as db:
        record = db.get(Resume, resume_id)
        storage_key = record.storage_key

    stored_path = resume_context["storage"] / storage_key
    assert stored_path.read_bytes() == content

    def fail_commit(self):
        raise RuntimeError("Simulated database commit failure")

    monkeypatch.setattr(resumes_api.Session, "commit", fail_commit)

    response = client.delete(f"/api/resumes/{resume_id}")

    assert response.status_code == 500
    assert "restored" in response.json()["detail"]
    assert stored_path.is_file()
    assert stored_path.read_bytes() == content

    with resume_context["factory"]() as db:
        assert db.get(Resume, resume_id) is not None

def test_upload_database_and_storage_cleanup_failure_logs_orphan(
    resume_context, monkeypatch, caplog
):
    client = resume_context["client"]

    def fail_commit(self):
        raise RuntimeError("Simulated upload database failure")

    def fail_delete(*args, **kwargs):
        raise OSError("Simulated storage cleanup failure")

    monkeypatch.setattr(resumes_api.Session, "commit", fail_commit)
    monkeypatch.setattr(
        resumes_api.resume_storage, "delete_resume", fail_delete
    )

    with caplog.at_level("ERROR", logger="app.api.resumes"):
        with pytest.raises(RuntimeError, match="Simulated upload database failure"):
            upload(client, "orphan.pdf", b"%PDF-1.7\\norphan")

    stored_files = list(resume_context["storage"].glob("*"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == b"%PDF-1.7\\norphan"
    assert "Failed to clean up resume storage" in caplog.text
    assert client.get("/api/resumes").json() == []
