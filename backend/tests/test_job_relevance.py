import pytest

from app.services.job_relevance import score_job_relevance


def test_junior_python_backend_role_scores_highly():
    result = score_job_relevance(
        {
            "title": "Junior Python Backend Developer",
            "description": "Build APIs with FastAPI and PostgreSQL.",
            "employment_type": "Full-time",
        }
    )

    assert result["score"] >= 60
    assert "Python/backend" in result["matched_role_families"]
    assert any("job title" in reason for reason in result["reasons"])


def test_react_role_matches_frontend_family():
    result = score_job_relevance(
        {
            "title": "Frontend Engineer",
            "description": "Build accessible interfaces using React and TypeScript.",
        }
    )

    assert "React/frontend" in result["matched_role_families"]
    assert result["score"] > 0


def test_full_stack_role_matches_full_stack_family():
    result = score_job_relevance(
        {
            "title": "Graduate Full-Stack Developer",
            "description": "Build web applications.",
        }
    )

    assert "Full-stack" in result["matched_role_families"]
    assert result["score"] >= 45


def test_unrelated_role_scores_zero():
    result = score_job_relevance(
        {
            "title": "Accountant",
            "description": "Prepare monthly financial reports.",
        }
    )

    assert result["score"] == 0
    assert result["matched_role_families"] == []


def test_empty_job_is_handled():
    result = score_job_relevance({})

    assert result["score"] == 0
    assert result["matched_role_families"] == []
    assert result["reasons"]


def test_senior_role_is_penalized():
    junior = score_job_relevance(
        {"title": "Python Developer"}
    )
    senior = score_job_relevance(
        {"title": "Senior Python Developer"}
    )

    assert senior["score"] < junior["score"]


def test_score_never_exceeds_one_hundred():
    result = score_job_relevance(
        {
            "title": "Junior Full-Stack Python React Developer",
            "description": (
                "Python FastAPI Django Flask backend APIs; "
                "React Next.js JavaScript TypeScript frontend."
            ),
        }
    )

    assert 0 <= result["score"] <= 100


@pytest.mark.parametrize(
    ("title", "expected_family"),
    [
        ("Python Developer", "Python/backend"),
        ("React Developer", "React/frontend"),
        ("Full-Stack Developer", "Full-stack"),
    ],
)
def test_target_role_families(title, expected_family):
    result = score_job_relevance({"title": title})

    assert expected_family in result["matched_role_families"]
