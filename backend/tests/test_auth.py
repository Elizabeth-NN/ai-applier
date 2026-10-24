from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.core.auth as auth


def make_request():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/jobs",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


def mock_verified_claims(monkeypatch, payload, signed_in=True):
    state = SimpleNamespace(
        is_signed_in=signed_in,
        payload=payload,
    )
    monkeypatch.setattr(
        auth,
        "authenticate_request",
        lambda request, options: state,
    )


def test_admin_role_is_accepted(monkeypatch):
    mock_verified_claims(
        monkeypatch,
        {
            "sub": "user_admin",
            "metadata": {"role": "admin"},
        },
    )

    assert auth.require_admin(make_request()) == "user_admin"


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"role": "user"},
        {"role": ["admin"]},
    ],
)
def test_non_admin_claims_are_rejected(monkeypatch, metadata):
    mock_verified_claims(
        monkeypatch,
        {
            "sub": "user_regular",
            "metadata": metadata,
        },
    )

    with pytest.raises(HTTPException) as exc:
        auth.require_admin(make_request())

    assert exc.value.status_code == 403


def test_unsigned_session_is_rejected(monkeypatch):
    mock_verified_claims(
        monkeypatch,
        {"sub": "user_admin", "metadata": {"role": "admin"}},
        signed_in=False,
    )

    with pytest.raises(HTTPException) as exc:
        auth.require_admin(make_request())

    assert exc.value.status_code == 401


def test_missing_user_id_is_rejected(monkeypatch):
    mock_verified_claims(
        monkeypatch,
        {"metadata": {"role": "admin"}},
    )

    with pytest.raises(HTTPException) as exc:
        auth.require_admin(make_request())

    assert exc.value.status_code == 401
