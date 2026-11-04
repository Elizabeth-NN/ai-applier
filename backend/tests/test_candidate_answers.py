from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
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
                "db_factory": testing_session_local,
                "current_user": current_user,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_answer(
    client: TestClient,
    question_key: str = "python_experience",
    answer: str = "I have built Python applications.",
    question_label: str = "Python experience",
    confirm_user_authored: bool = True,
    question_aliases: list[str] | None = None,
):
    return client.post(
        "/api/candidate-answers",
        json={
            "question_key": question_key,
            "question_label": question_label,
            "question_aliases": question_aliases or [],
            "answer": answer,
            "confirm_user_authored": confirm_user_authored,
        },
    )


def test_create_answer_requires_explicit_authorship_confirmation(test_context):
    response = test_context["client"].post(
        "/api/candidate-answers",
        json={
            "question_key": "python_experience",
            "question_label": "Python experience",
            "answer": "My own answer.",
        },
    )

    assert response.status_code == 422


def test_create_answer_rejects_false_authorship_confirmation(test_context):
    response = create_answer(
        test_context["client"],
        confirm_user_authored=False,
    )

    assert response.status_code == 422


def test_new_answer_is_user_authored_but_not_approved(test_context):
    response = create_answer(test_context["client"])

    assert response.status_code == 201
    data = response.json()
    assert data["question_key"] == "python_experience"
    assert data["answer"] == "I have built Python applications."
    assert data["is_user_authored"] is True
    assert data["is_approved"] is False


def test_create_rejects_whitespace_only_answer(test_context):
    response = create_answer(
        test_context["client"],
        answer="   ",
    )

    assert response.status_code == 422


def test_create_rejects_duplicate_question_key_for_same_user(test_context):
    client = test_context["client"]

    first = create_answer(client)
    second = create_answer(
        client,
        answer="A different answer.",
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_different_users_can_use_the_same_question_key(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]

    first = create_answer(client)
    current_user["id"] = "user_test_2"
    second = create_answer(client)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_list_only_returns_current_users_answers(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]

    first = create_answer(client)
    assert first.status_code == 201

    current_user["id"] = "user_test_2"
    second = create_answer(client)

    assert second.status_code == 201

    response = client.get("/api/candidate-answers")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        second.json()["id"]
    ]


def test_owner_can_read_and_update_answer(test_context):
    client = test_context["client"]
    created = create_answer(client)
    answer_id = created.json()["id"]

    read_response = client.get(f"/api/candidate-answers/{answer_id}")

    assert read_response.status_code == 200
    assert read_response.json()["answer"] == "I have built Python applications."

    update_response = client.patch(
        f"/api/candidate-answers/{answer_id}",
        json={
            "question_label": "Updated Python experience",
            "answer": "I built and maintained Python APIs.",
            "confirm_user_authored": True,
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["question_label"] == "Updated Python experience"
    assert update_response.json()["answer"] == "I built and maintained Python APIs."
    assert update_response.json()["is_user_authored"] is True
    assert update_response.json()["is_approved"] is False


def test_user_cannot_read_update_approve_or_delete_another_users_answer(
    test_context,
):
    client = test_context["client"]
    current_user = test_context["current_user"]

    created = create_answer(client)
    answer_id = created.json()["id"]

    current_user["id"] = "user_test_2"

    assert client.get(
        f"/api/candidate-answers/{answer_id}"
    ).status_code == 404

    assert client.patch(
        f"/api/candidate-answers/{answer_id}",
        json={
            "question_label": "Attempted edit",
            "answer": "Attempted answer",
            "confirm_user_authored": True,
        },
    ).status_code == 404

    assert client.post(
        f"/api/candidate-answers/{answer_id}/approve"
    ).status_code == 404

    assert client.delete(
        f"/api/candidate-answers/{answer_id}"
    ).status_code == 404


def test_owner_can_approve_user_authored_answer(test_context):
    client = test_context["client"]
    created = create_answer(client)
    answer_id = created.json()["id"]

    response = client.post(
        f"/api/candidate-answers/{answer_id}/approve"
    )

    assert response.status_code == 200
    assert response.json()["is_user_authored"] is True
    assert response.json()["is_approved"] is True


def test_editing_answer_revokes_previous_approval(test_context):
    client = test_context["client"]
    created = create_answer(client)
    answer_id = created.json()["id"]

    approved = client.post(
        f"/api/candidate-answers/{answer_id}/approve"
    )
    assert approved.status_code == 200
    assert approved.json()["is_approved"] is True

    updated = client.patch(
        f"/api/candidate-answers/{answer_id}",
        json={
            "question_label": "Python experience",
            "answer": "I have revised my own answer.",
            "confirm_user_authored": True,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["is_user_authored"] is True
    assert updated.json()["is_approved"] is False


def test_update_rejects_whitespace_only_answer(test_context):
    client = test_context["client"]
    created = create_answer(client)
    answer_id = created.json()["id"]

    response = client.patch(
        f"/api/candidate-answers/{answer_id}",
        json={
            "question_label": "Python experience",
            "answer": "   ",
            "confirm_user_authored": True,
        },
    )

    assert response.status_code == 422


def test_owner_can_delete_answer(test_context):
    client = test_context["client"]
    created = create_answer(client)
    answer_id = created.json()["id"]

    response = client.delete(
        f"/api/candidate-answers/{answer_id}"
    )

    assert response.status_code == 204
    assert client.get(
        f"/api/candidate-answers/{answer_id}"
    ).status_code == 404



def test_create_answer_normalizes_and_deduplicates_question_aliases(test_context):
    response = create_answer(
        test_context["client"],
        question_aliases=[
            "  Briefly describe your Python experience  ",
            "briefly describe your python experience",
            "Python experience",
        ],
    )

    assert response.status_code == 201
    assert response.json()["question_aliases"] == [
        "Briefly describe your Python experience"
    ]


def test_create_answer_defaults_to_no_question_aliases(test_context):
    response = create_answer(test_context["client"])

    assert response.status_code == 201
    assert response.json()["question_aliases"] == []


def test_create_answer_rejects_empty_question_alias(test_context):
    response = create_answer(
        test_context["client"],
        question_aliases=["   "],
    )

    assert response.status_code == 422


def test_create_answer_rejects_more_than_twenty_question_aliases(test_context):
    response = create_answer(
        test_context["client"],
        question_aliases=[f"Alternative question {index}" for index in range(21)],
    )

    assert response.status_code == 422


def test_updating_aliases_revokes_previous_approval(test_context):
    client = test_context["client"]
    created = create_answer(client)
    answer_id = created.json()["id"]

    approved = client.post(f"/api/candidate-answers/{answer_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["is_approved"] is True

    updated = client.patch(
        f"/api/candidate-answers/{answer_id}",
        json={
            "question_label": "Python experience",
            "question_aliases": [
                "Briefly describe your Python software development experience"
            ],
            "answer": "I have built Python backend applications.",
            "confirm_user_authored": True,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["question_aliases"] == [
        "Briefly describe your Python software development experience"
    ]
    assert updated.json()["is_user_authored"] is True
    assert updated.json()["is_approved"] is False


def test_update_without_aliases_preserves_existing_aliases(test_context):
    client = test_context["client"]
    created = create_answer(
        client,
        question_aliases=["Tell us about your Python experience"],
    )
    answer_id = created.json()["id"]

    updated = client.patch(
        f"/api/candidate-answers/{answer_id}",
        json={
            "question_label": "Python experience",
            "answer": "I have updated my Python experience.",
            "confirm_user_authored": True,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["question_aliases"] == [
        "Tell us about your Python experience"
    ]
    assert updated.json()["is_approved"] is False
