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



def test_r2_settings_load_from_env_file(monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "r2")
    for name in (
        "R2_ENDPOINT_URL",
        "R2_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(
        resume_storage,
        "dotenv_values",
        lambda path: {
            "R2_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
            "R2_BUCKET": "private-resumes",
            "R2_ACCESS_KEY_ID": "file-access-key",
            "R2_SECRET_ACCESS_KEY": "file-secret-key",
        },
    )

    config = resume_storage._r2_settings()
    assert config["bucket"] == "private-resumes"
    assert config["access_key_id"] == "file-access-key"


def test_process_environment_overrides_env_file(monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "r2")
    monkeypatch.setenv("R2_BUCKET", "environment-bucket")

    monkeypatch.setattr(
        resume_storage,
        "dotenv_values",
        lambda path: {"R2_BUCKET": "file-bucket"},
    )

    assert resume_storage._setting("R2_BUCKET") == "environment-bucket"


def test_r2_storage_round_trip_with_mock_client(monkeypatch):
    from io import BytesIO
    from types import ModuleType, SimpleNamespace
    import sys

    monkeypatch.setenv("RESUME_STORAGE_BACKEND", "r2")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_BUCKET", "private-resumes")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("R2_REGION", "auto")
    monkeypatch.setenv("R2_PREFIX", "resumes")

    calls = []
    stored = {}

    class FakeS3Client:
        def put_object(self, **kwargs):
            calls.append(("put", kwargs))
            stored[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            calls.append(("get", kwargs))
            return {"Body": BytesIO(stored[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs))
            stored.pop(kwargs["Key"], None)

    fake_client = FakeS3Client()
    fake_boto3 = ModuleType("boto3")

    def fake_client_factory(service, **kwargs):
        assert service == "s3"
        assert kwargs["endpoint_url"] == "https://example.r2.cloudflarestorage.com"
        assert kwargs["region_name"] == "auto"
        return fake_client

    fake_boto3.client = fake_client_factory
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    resume_storage.put_resume(
        "resume.pdf",
        b"private resume",
        content_type="application/pdf",
    )
    assert resume_storage.read_resume("resume.pdf") == b"private resume"
    resume_storage.delete_resume("resume.pdf")

    assert [call[0] for call in calls] == ["put", "get", "delete"]
    assert calls[0][1]["Bucket"] == "private-resumes"
    assert calls[0][1]["Key"] == "resumes/resume.pdf"
    assert calls[0][1]["ContentType"] == "application/pdf"
    assert "ACL" not in calls[0][1]
    assert calls[1][1]["Key"] == "resumes/resume.pdf"
    assert calls[2][1]["Key"] == "resumes/resume.pdf"
    assert stored == {}
