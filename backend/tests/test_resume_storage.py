from pathlib import Path

import pytest

from app.services import resume_storage


def test_local_storage_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "local")

    resume_storage.put_resume(
        "resume.pdf",
        b"%PDF-example",
        local_dir=tmp_path,
    )

    assert resume_storage.read_resume(
        "resume.pdf",
        local_dir=tmp_path,
    ) == b"%PDF-example"

    resume_storage.delete_resume("resume.pdf", local_dir=tmp_path)
    assert not (tmp_path / "resume.pdf").exists()


def test_local_storage_does_not_overwrite_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "local")
    (tmp_path / "resume.pdf").write_bytes(b"original")

    with pytest.raises(FileExistsError):
        resume_storage.put_resume(
            "resume.pdf",
            b"replacement",
            local_dir=tmp_path,
        )

    assert (tmp_path / "resume.pdf").read_bytes() == b"original"


@pytest.mark.parametrize("key", ["", "../resume.pdf", "/resume.pdf", "a/b.pdf", ".."])
def test_rejects_unsafe_storage_keys(key):
    with pytest.raises(ValueError):
        resume_storage.read_resume(key)


def test_r2_requires_all_configuration(monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "r2")
    for name in (
        "R2_ENDPOINT_URL",
        "R2_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="R2 storage is selected"):
        resume_storage.put_resume("resume.pdf", b"content")


def test_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "unknown")

    with pytest.raises(RuntimeError, match="RESUME_STORAGE_BACKEND"):
        resume_storage.read_resume("resume.pdf")
