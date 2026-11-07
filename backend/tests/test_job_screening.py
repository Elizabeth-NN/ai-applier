import pytest

from app.services.job_screening import screen_job


def base_job(**overrides):
    job = {
        "title": "Junior Python Developer",
        "description": "Build backend APIs with Python and FastAPI.",
        "employment_type": "Full-time",
        "remote_type": "remote",
        "eligibility_status": "eligible",
        "eligible_countries": ["Kenya"],
        "listing_status": "active",
    }
    job.update(overrides)
    return job


def test_prioritizes_a_verified_remote_junior_job():
    result = screen_job(
        base_job(),
        {
            "target_roles": ["Junior Python Developer"],
            "work_preferences": {
                "remote": True,
                "employment_type": ["full-time"],
            },
        },
        {"profile_match_score": 82, "match_score": 70},
    )

    assert result["recommendation"] == "prioritize"
    assert result["role_alignment"] == "aligned"
    assert result["experience_fit"] == "aligned"
    assert result["remote_fit"] == "aligned"
    assert result["employment_fit"] == "aligned"
    assert result["kenya_eligibility"] == "eligible"
    assert result["listing_status"] == "active"
    assert result["match_score"] == 82


@pytest.mark.parametrize(
    ("overrides", "dimension", "expected"),
    [
        (
            {"eligibility_status": "ineligible"},
            "kenya_eligibility",
            "ineligible",
        ),
        (
            {"listing_status": "closed"},
            "listing_status",
            "closed",
        ),
    ],
)
def test_excludes_confirmed_disqualifiers(overrides, dimension, expected):
    result = screen_job(base_job(**overrides))

    assert result["recommendation"] == "exclude"
    assert result[dimension] == expected


def test_unknown_eligibility_and_listing_require_review():
    result = screen_job(
        base_job(
            eligibility_status="unknown",
            eligible_countries=None,
            listing_status="unknown",
        )
    )

    assert result["recommendation"] == "review"
    assert result["kenya_eligibility"] == "unknown"
    assert result["listing_status"] == "unknown"
    assert any("Kenya" in reason for reason in result["reasons"])


def test_unknown_remote_type_does_not_become_a_disqualifier():
    result = screen_job(
        base_job(remote_type=None),
        {"work_preferences": {"remote": True}},
    )

    assert result["recommendation"] == "review"
    assert result["remote_fit"] == "unknown"


def test_remote_preference_mismatch_requires_review_not_exclusion():
    result = screen_job(
        base_job(remote_type="onsite"),
        {"work_preferences": {"remote": True}},
    )

    assert result["recommendation"] == "review"
    assert result["remote_fit"] == "mismatch"


def test_senior_role_is_flagged_for_review_not_automatically_excluded():
    result = screen_job(
        base_job(title="Senior Python Engineer")
    )

    assert result["recommendation"] == "review"
    assert result["experience_level"] == "senior"
    assert result["experience_fit"] == "mismatch"


def test_malformed_preferences_are_ignored_safely():
    result = screen_job(
        base_job(),
        {
            "target_roles": "not a list",
            "work_preferences": {
                "remote": "true",
                "employment_type": "full-time",
            },
        },
    )

    assert result["remote_fit"] == "not_specified"
    assert result["employment_fit"] == "not_specified"
    assert result["recommendation"] == "prioritize"


def test_eligible_status_conflicting_with_country_list_requires_review():
    result = screen_job(
        base_job(eligible_countries=["United States"])
    )

    assert result["recommendation"] == "review"
    assert result["kenya_eligibility"] == "conflicting_evidence"


def test_match_score_is_context_not_a_disqualifier():
    result = screen_job(
        base_job(),
        match={"match_score": 5},
    )

    assert result["match_score"] == 5
    assert result["recommendation"] == "prioritize"


@pytest.mark.parametrize(
    ("employment_type", "expected_fit"),
    [
        ("Full-Time", "aligned"),
        ("Full Time", "aligned"),
        ("Full-time", "aligned"),
        ("Contract", "aligned"),
        ("Contractor", "aligned"),
        ("Contract-based", "aligned"),
        ("Full-time, Contract", "aligned"),
        ("Full-time / Contract", "aligned"),
        ("Part-Time", "mismatch"),
        ("Internship", "mismatch"),
    ],
)
def test_employment_type_preferences_are_normalized(
    employment_type,
    expected_fit,
):
    result = screen_job(
        base_job(employment_type=employment_type),
        {
            "work_preferences": {
                "remote": True,
                "employment_type": ["full-time", "contract"],
            }
        },
    )

    assert result["employment_fit"] == expected_fit

    if expected_fit == "mismatch":
        assert result["recommendation"] == "review"
    else:
        assert result["recommendation"] == "prioritize"


def test_multiple_preferred_employment_types_are_normalized():
    result = screen_job(
        base_job(employment_type="Contractor"),
        {
            "work_preferences": {
                "employment_type": ["Full Time", "Contractor"],
            }
        },
    )

    assert result["employment_fit"] == "aligned"
    assert result["recommendation"] == "prioritize"
