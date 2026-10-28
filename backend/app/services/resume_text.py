"""Extract readable text from privately stored resumes."""

import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException
from pypdf import PdfReader


def extract_resume_text(path: Path, filename: str) -> str:
    """Extract readable text from a PDF or DOCX resume."""
    try:
        content = path.read_bytes()

        if filename.lower().endswith(".pdf"):
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise HTTPException(
                    status_code=422,
                    detail="The selected PDF is encrypted. Upload an unlocked PDF.",
                )

            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )

        elif filename.lower().endswith(".docx"):
            with ZipFile(BytesIO(content)) as archive:
                xml_content = archive.read("word/document.xml")

            root = ET.fromstring(xml_content)
            namespace = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            }
            paragraphs = []

            for paragraph in root.findall(".//w:p", namespace):
                words = [
                    node.text or ""
                    for node in paragraph.findall(".//w:t", namespace)
                ]
                paragraphs.append("".join(words))

            text = "\n".join(paragraphs)

        else:
            raise HTTPException(
                status_code=422,
                detail="Only PDF and DOCX resumes are supported.",
            )

    except HTTPException:
        raise
    except (
        OSError,
        ValueError,
        BadZipFile,
        ET.ParseError,
        KeyError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail="The selected resume could not be read. Upload a valid PDF or DOCX.",
        ) from exc

    text = text.strip()
    if len(text) < 40:
        raise HTTPException(
            status_code=422,
            detail="Not enough readable text was found. Try a text-based PDF or DOCX.",
        )

    return text[:8000]
