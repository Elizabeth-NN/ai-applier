from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_user
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app


@pytest.fixture
def test_context() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    current_user = {"id": "user_test_1"}

    def override_get_db():
        db = testing_session_local()
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
                "current_user": current_user,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_get_profile_returns_null_when_profile_does_not_exist(test_context):
    response = test_context["client"].get("/api/candidate-profile")

    assert response.status_code == 200
    assert response.json() is None


def test_create_profile_with_defaults(test_context):
    response = test_context["client"].put(
        "/api/candidate-profile",
        json={"full_name": "Elizabeth Njuguna"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["full_name"] == "Elizabeth Njuguna"
    assert data["skills"] == []
    assert data["experience"] == []
    assert data["education"] == []
    assert data["projects"] == []
    assert data["certifications"] == []
    assert data["links"] == {}
    assert data["target_roles"] == []
    assert data["work_preferences"] == {}
    assert data["id"] is not None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_create_profile_trims_optional_text_and_string_lists(test_context):
    response = test_context["client"].put(
        "/api/candidate-profile",
        json={
            "full_name": "  Elizabeth Njuguna  ",
            "headline": "  Junior Software Developer  ",
            "skills": [" Python ", "React", ""],
            "target_roles": [" Backend Developer ", ""],
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["full_name"] == "Elizabeth Njuguna"
    assert data["headline"] == "Junior Software Developer"
    assert data["skills"] == ["Python", "React"]
    assert data["target_roles"] == ["Backend Developer"]


def test_create_profile_preserves_structured_sections(test_context):
    profile = {
        "full_name": "Elizabeth Njuguna",
        "skills": ["Python", "FastAPI"],
        "experience": [
            {
                "company": "Example Tech",
                "title": "Software Engineering Intern",
                "description": "Built backend APIs.",
            }
        ],
        "education": [
            {
                "institution": "Moringa School",
                "qualification": "Software Engineering",
            }
        ],
        "projects": [
            {
                "name": "AI Applier",
                "description": "Job application assistant.",
            }
        ],
        "certifications": [
            {
                "name": "Python Certification",
                "issuer": "Example Provider",
            }
        ],
        "links": {
            "github": "https://github.com/example",
            "linkedin": "https://linkedin.com/in/example",
        },
        "target_roles": ["Junior Python Developer"],
        "work_preferences": {
            "remote": True,
            "employment_type": ["full-time"],
        },
    }

    response = test_context["client"].put(
        "/api/candidate-profile",
        json=profile,
    )

    assert response.status_code == 200

    data = response.json()
    for field, expected in profile.items():
        assert data[field] == expected


def test_put_updates_existing_profile_without_creating_duplicate(test_context):
    client = test_context["client"]

    first = client.put(
        "/api/candidate-profile",
        json={
            "full_name": "Elizabeth Njuguna",
            "skills": ["Python"],
        },
    )
    assert first.status_code == 200

    second = client.put(
        "/api/candidate-profile",
        json={
            "full_name": "Elizabeth Njuguna",
            "headline": "Junior Backend Developer",
            "skills": ["Python", "FastAPI"],
        },
    )

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["headline"] == "Junior Backend Developer"
    assert second.json()["skills"] == ["Python", "FastAPI"]

    read_response = client.get("/api/candidate-profile")
    assert read_response.status_code == 200
    assert read_response.json()["id"] == first.json()["id"]


def test_put_replaces_omitted_fields_with_defaults(test_context):
    client = test_context["client"]

    first = client.put(
        "/api/candidate-profile",
        json={
            "full_name": "Elizabeth Njuguna",
            "skills": ["Python", "React"],
            "target_roles": ["Backend Developer"],
        },
    )
    assert first.status_code == 200

    second = client.put(
        "/api/candidate-profile",
        json={"full_name": "Elizabeth Njuguna"},
    )

    assert second.status_code == 200
    assert second.json()["skills"] == []
    assert second.json()["target_roles"] == []


def test_different_users_have_separate_profiles(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]

    first = client.put(
        "/api/candidate-profile",
        json={
            "full_name": "First User",
            "skills": ["Python"],
        },
    )
    assert first.status_code == 200

    current_user["id"] = "user_test_2"

    second_user_read = client.get("/api/candidate-profile")
    assert second_user_read.status_code == 200
    assert second_user_read.json() is None

    second = client.put(
        "/api/candidate-profile",
        json={
            "full_name": "Second User",
            "skills": ["JavaScript"],
        },
    )
    assert second.status_code == 200
    assert second.json()["id"] != first.json()["id"]

    current_user["id"] = "user_test_1"

    first_user_read = client.get("/api/candidate-profile")
    assert first_user_read.status_code == 200
    assert first_user_read.json()["full_name"] == "First User"
    assert first_user_read.json()["skills"] == ["Python"]


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "A" * 256},
        {"email": "a" * 321},
        {"professional_summary": "A" * 10001},
        {"skills": ["Python"] * 101},
        {"experience": [{}] * 51},
        {"education": [{}] * 31},
        {"projects": [{}] * 51},
        {"certifications": [{}] * 51},
        {"target_roles": ["Developer"] * 31},
    ],
)
def test_profile_rejects_values_over_field_limits(test_context, payload):
    response = test_context["client"].put(
        "/api/candidate-profile",
        json=payload,
    )

    assert response.status_code == 422


def test_profile_rejects_invalid_string_list_items(test_context):
    response = test_context["client"].put(
        "/api/candidate-profile",
        json={"skills": [123]},
    )

    assert response.status_code == 422


def test_profile_data_is_persisted_after_another_request(test_context):
    client = test_context["client"]

    created = client.put(
        "/api/candidate-profile",
        json={
            "full_name": "Elizabeth Njuguna",
            "skills": ["Python", "FastAPI"],
        },
    )
    assert created.status_code == 200

    retrieved = client.get("/api/candidate-profile")

    assert retrieved.status_code == 200
    assert retrieved.json()["id"] == created.json()["id"]
    assert retrieved.json()["full_name"] == "Elizabeth Njuguna"
    assert retrieved.json()["skills"] == ["Python", "FastAPI"]
