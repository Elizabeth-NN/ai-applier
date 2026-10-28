from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException
from pypdf import PdfWriter

from app.services.resume_text import extract_resume_text


def create_docx(path, text):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
    </w:document>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)


def test_extracts_text_from_docx(tmp_path):
    text = (
        "Software developer with Python, FastAPI, PostgreSQL and Docker "
        "experience. Built and tested web applications and REST APIs."
    )
    path = tmp_path / "resume.docx"
    create_docx(path, text)

    assert extract_resume_text(path, "resume.docx") == text


def test_rejects_unsupported_file_type(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("This is a text file with enough characters to be readable.")

    with pytest.raises(HTTPException) as error:
        extract_resume_text(path, "resume.txt")

    assert error.value.status_code == 422
    assert error.value.detail == "Only PDF and DOCX resumes are supported."


def test_rejects_corrupt_docx(tmp_path):
    path = tmp_path / "resume.docx"
    path.write_text("This is not a valid DOCX archive.")

    with pytest.raises(HTTPException) as error:
        extract_resume_text(path, "resume.docx")

    assert error.value.status_code == 422
    assert error.value.detail == (
        "The selected resume could not be read. Upload a valid PDF or DOCX."
    )


def test_rejects_docx_with_too_little_text(tmp_path):
    path = tmp_path / "resume.docx"
    create_docx(path, "Too short")

    with pytest.raises(HTTPException) as error:
        extract_resume_text(path, "resume.docx")

    assert error.value.status_code == 422
    assert error.value.detail == (
        "Not enough readable text was found. "
        "Try a text-based PDF or DOCX."
    )


def test_limits_extracted_text_to_8000_characters(tmp_path):
    path = tmp_path / "resume.docx"
    create_docx(path, "A" * 9000)

    result = extract_resume_text(path, "resume.docx")

    assert len(result) == 8000
    assert result == "A" * 8000


def test_rejects_encrypted_pdf(tmp_path):
    path = tmp_path / "encrypted.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("test-password")

    with path.open("wb") as output:
        writer.write(output)

    with pytest.raises(HTTPException) as error:
        extract_resume_text(path, "encrypted.pdf")

    assert error.value.status_code == 422
    assert error.value.detail == (
        "The selected PDF is encrypted. Upload an unlocked PDF."
    )
