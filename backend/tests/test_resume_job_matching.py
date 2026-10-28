from app.services.resume_job_matching import (
    score_resume_job_match,
)


def test_matching_uses_terms_from_the_supplied_documents():
    result = score_resume_job_match(
        "I built an inventory platform using Python, FastAPI, and PostgreSQL.",
        title="Junior Python Developer",
        description=(
            "Build APIs with Python and FastAPI. "
            "Experience with PostgreSQL and Docker."
        ),
    )

    assert result["match_score"] > 0
    assert "python" in result["matched_terms"]
    assert "fastapi" in result["matched_terms"]
    assert "docker" in result["terms_not_found_in_resume"]
    assert result["match_reasons"]


def test_new_terms_are_matched_without_adding_them_to_a_catalogue():
    result = score_resume_job_match(
        "Created workflows using Temporal and event-driven architecture.",
        title="Workflow Engineer",
        description="Build workflows with Temporal and event-driven architecture.",
    )

    assert "temporal" in result["matched_terms"]
    assert "event driven architecture" in result["matched_terms"]


def test_no_informative_job_text_returns_an_explanation():
    result = score_resume_job_match(
        "Python developer building web applications.",
        title="The and or",
        description="",
    )

    assert result["match_score"] == 0
    assert result["matched_terms"] == []
    assert result["match_reasons"]


def test_score_is_bounded():
    result = score_resume_job_match(
        "Python FastAPI PostgreSQL Docker",
        title="Python Developer",
        description="Python FastAPI PostgreSQL Docker",
    )

    assert 0 <= result["match_score"] <= 100


def test_matching_does_not_claim_missing_terms_are_missing_skills():
    result = score_resume_job_match(
        "I build web applications.",
        title="Developer",
        description="Experience with Temporal workflows.",
    )

    assert "temporal" in result["terms_not_found_in_resume"]
    assert not any(
        "lack" in reason.casefold() or "don't have" in reason.casefold()
        for reason in result["match_reasons"]
    )
