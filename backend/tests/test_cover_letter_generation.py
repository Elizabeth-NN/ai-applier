from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.api import cover_letter_generation as generation_api
from app.core.config import settings
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from test_cover_letter_drafts import create_saved_application, test_context


def create_docx(path):
    text = (
        "Software developer with Python, FastAPI, PostgreSQL and Docker "
        "experience. Built and tested web applications and REST APIs."
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
    </w:document>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    return text


def prepare_generation(test_context, monkeypatch, resume_owner="user_test_1"):
    from pathlib import Path

    storage = Path(monkeypatch.tempdir) if hasattr(monkeypatch, "tempdir") else None
    # pytest's tmp_path is supplied by each test instead; this helper only
    # prepares the database records and resume metadata.
    application_id = create_saved_application(test_context["db_factory"])

    with test_context["db_factory"]() as db:
        application = db.get(Application, application_id)
        job = db.get(Job, application.job_id)
        job.description = (
            "We need a junior Python developer to build and maintain "
            "REST APIs, write tests, and work with PostgreSQL."
        )

        resume = Resume(
            user_id=resume_owner,
            original_filename="resume.docx",
            storage_key="resume.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            size_bytes=1,
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        resume_id = resume.id

    return application_id, resume_id


def mock_gemini(
    monkeypatch,
    response_text=(
        "<cover_letter>Dear Hiring Manager,\\n\\n"
        "I am applying for this role because my experience building and "
        "testing web applications aligns with the position. I have worked "
        "with Python, FastAPI, PostgreSQL, and Docker, and I look forward "
        "to contributing these skills while continuing to grow as a "
        "software developer.\\n\\nSincerely,\\nElizabeth"
        "</cover_letter>"
    ),
):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": response_text}]}}
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(generation_api.httpx, "post", fake_post)
    monkeypatch.setattr(settings, "gemini_api_key", "test-api-key")
    return captured


def test_generates_cover_letter_from_owned_resume(
    test_context, monkeypatch, tmp_path
):
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path))
    resume_text = create_docx(tmp_path / "resume.docx")
    application_id, resume_id = prepare_generation(test_context, monkeypatch)
    captured = mock_gemini(monkeypatch)

    response = test_context["client"].post(
        "/api/cover-letter-generation",
        json={"application_id": application_id, "resume_id": resume_id},
    )

    assert response.status_code == 200, response.text
    assert response.json()["content"].startswith("Dear Hiring Manager")
    assert "Junior Python Developer" in captured["json"]["contents"][0]["parts"][0]["text"]
    assert resume_text in captured["json"]["contents"][0]["parts"][0]["text"]
    assert captured["headers"]["x-goog-api-key"] == "test-api-key"


def test_generation_requires_gemini_api_key(test_context, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    application_id = create_saved_application(test_context["db_factory"])

    response = test_context["client"].post(
        "/api/cover-letter-generation",
        json={"application_id": application_id, "resume_id": 1},
    )

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_cannot_generate_with_another_users_resume(
    test_context, monkeypatch, tmp_path
):
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path))
    create_docx(tmp_path / "resume.docx")
    application_id, resume_id = prepare_generation(
        test_context, monkeypatch, resume_owner="user_test_2"
    )
    mock_gemini(monkeypatch)

    response = test_context["client"].post(
        "/api/cover-letter-generation",
        json={"application_id": application_id, "resume_id": resume_id},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found."
