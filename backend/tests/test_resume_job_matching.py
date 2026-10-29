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


def test_role_aligned_resume_scores_higher_than_unrelated_resume():
    job = {
        "title": "Junior Python Backend Developer",
        "description": (
            "Build backend APIs using Python, FastAPI, and PostgreSQL."
        ),
    }

    aligned = score_resume_job_match(
        "Python backend developer. Built APIs using Python, FastAPI, PostgreSQL.",
        **job,
    )
    unrelated = score_resume_job_match(
        "Graphic designer. Created brand identities, marketing campaigns, and illustrations.",
        **job,
    )

    assert aligned["match_score"] > unrelated["match_score"]


def test_repeating_the_same_job_description_does_not_change_its_score():
    title = "Python Backend Developer"
    description = "Build APIs using Python and FastAPI."

    single = score_resume_job_match(
        "Python developer building APIs with FastAPI.",
        title=title,
        description=description,
    )
    repeated = score_resume_job_match(
        "Python developer building APIs with FastAPI.",
        title=title,
        description=f"{description} {description} {description}",
    )

    assert repeated["match_score"] == single["match_score"]


def test_matching_the_job_title_improves_the_score():
    title = "Python Backend Developer"
    description = (
        "Work with a collaborative team to deliver reliable "
        "software products and meet project deadlines."
    )

    title_aligned = score_resume_job_match(
        "Python backend developer with experience building APIs.",
        title=title,
        description=description,
    )
    generic_overlap = score_resume_job_match(
        "Collaborative professional delivering reliable software "
        "products and meeting project deadlines.",
        title=title,
        description=description,
    )

    assert title_aligned["match_score"] > generic_overlap["match_score"]


def test_explicit_requirement_matters_more_than_generic_description_overlap():
    title = "Backend Developer"
    description = (
        "Required: PostgreSQL experience. "
        "We value collaboration and clear communication."
    )

    requirement_aligned = score_resume_job_match(
        "Backend developer experienced with PostgreSQL.",
        title=title,
        description=description,
    )
    generic_overlap = score_resume_job_match(
        "Backend developer skilled in collaboration and clear communication.",
        title=title,
        description=description,
    )

    assert (
        requirement_aligned["match_score"]
        > generic_overlap["match_score"]
    )


def test_prepared_resume_features_preserve_match_results():
    from app.services.resume_job_matching import prepare_resume_features

    resume_text = (
        "Python backend developer. "
        "Built APIs using Python, FastAPI, PostgreSQL and Docker."
    )
    job = {
        "title": "Junior Python Backend Developer",
        "description": (
            "Required: Python, FastAPI and PostgreSQL. "
            "Build APIs and deploy with Docker."
        ),
        "employment_type": "Full-time",
    }

    original = score_resume_job_match(resume_text, **job)
    prepared = score_resume_job_match(
        resume_text,
        **job,
        prepared_resume_features=prepare_resume_features(resume_text),
    )

    assert prepared == original
