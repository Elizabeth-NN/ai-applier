"""Private resume storage with local and optional S3-compatible backends."""

import os
from pathlib import Path, PurePosixPath
from typing import Any


def _backend() -> str:
    value = os.environ.get("RESUME_STORAGE_BACKEND", "local").strip().lower()
    if value not in {"local", "r2"}:
        raise RuntimeError(
            "RESUME_STORAGE_BACKEND must be either 'local' or 'r2'."
        )
    return value


def _local_dir(override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).resolve()

    configured = os.environ.get("RESUME_STORAGE_DIR")
    if configured:
        return Path(configured).resolve()

    return (
        Path(__file__).resolve().parents[2] / "private_uploads"
    ).resolve()


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if (
        not key
        or path.is_absolute()
        or len(path.parts) != 1
        or key in {".", ".."}
        or "\\" in key
    ):
        raise ValueError("Invalid resume storage key.")
    return key


def _r2_settings() -> dict[str, str]:
    names = {
        "endpoint_url": "R2_ENDPOINT_URL",
        "bucket": "R2_BUCKET",
        "access_key_id": "R2_ACCESS_KEY_ID",
        "secret_access_key": "R2_SECRET_ACCESS_KEY",
    }
    values = {
        key: os.environ.get(env_name, "").strip()
        for key, env_name in names.items()
    }
    missing = [
        names[key]
        for key, value in values.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "R2 storage is selected but these settings are missing: "
            + ", ".join(missing)
        )
    return values


def _s3_client() -> tuple[Any, str]:
    config = _r2_settings()

    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "R2 storage requires boto3. Install backend requirements."
        ) from exc

    client = boto3.client(
        "s3",
        endpoint_url=config["endpoint_url"],
        aws_access_key_id=config["access_key_id"],
        aws_secret_access_key=config["secret_access_key"],
        region_name=os.environ.get("R2_REGION", "auto"),
    )
    return client, config["bucket"]


def _object_key(key: str) -> str:
    safe_key = _safe_key(key)
    prefix = os.environ.get("R2_PREFIX", "").strip("/")
    return f"{prefix}/{safe_key}" if prefix else safe_key


def put_resume(
    key: str,
    content: bytes,
    *,
    content_type: str | None = None,
    local_dir: Path | None = None,
) -> None:
    """Store resume bytes privately."""
    safe_key = _safe_key(key)

    if _backend() == "local":
        directory = _local_dir(local_dir)
        directory.mkdir(parents=True, exist_ok=True)
        destination = (directory / safe_key).resolve()
        if destination.parent != directory:
            raise ValueError("Invalid resume storage key.")
        with destination.open("xb") as output:
            output.write(content)
        return

    client, bucket = _s3_client()
    arguments: dict[str, Any] = {
        "Bucket": bucket,
        "Key": _object_key(safe_key),
        "Body": content,
    }
    if content_type:
        arguments["ContentType"] = content_type
    client.put_object(**arguments)


def read_resume(
    key: str,
    *,
    local_dir: Path | None = None,
) -> bytes:
    """Read private resume bytes."""
    safe_key = _safe_key(key)

    if _backend() == "local":
        directory = _local_dir(local_dir)
        source = (directory / safe_key).resolve()
        if source.parent != directory:
            raise ValueError("Invalid resume storage key.")
        try:
            return source.read_bytes()
        except FileNotFoundError:
            raise

    client, bucket = _s3_client()
    response = client.get_object(
        Bucket=bucket,
        Key=_object_key(safe_key),
    )
    return response["Body"].read()


def delete_resume(
    key: str,
    *,
    local_dir: Path | None = None,
) -> None:
    """Delete a private resume object."""
    safe_key = _safe_key(key)

    if _backend() == "local":
        directory = _local_dir(local_dir)
        destination = (directory / safe_key).resolve()
        if destination.parent != directory:
            raise ValueError("Invalid resume storage key.")
        destination.unlink(missing_ok=True)
        return

    client, bucket = _s3_client()
    client.delete_object(
        Bucket=bucket,
        Key=_object_key(safe_key),
    )
