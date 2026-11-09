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


@pytest.mark.parametrize(
    ("job", "expected"),
    [
        ({"title": "Software Engineering Intern"}, "internship"),
        (
            {"title": "Python Developer", "employment_type": "Internship"},
            "internship",
        ),
        ({"title": "Graduate Software Engineer"}, "entry-level"),
        ({"title": "New Grad Backend Developer"}, "entry-level"),
        ({"title": "Trainee Python Developer"}, "entry-level"),
        ({"title": "Junior Python Developer"}, "junior"),
        ({"title": "Jr. Software Engineer"}, "junior"),
        ({"title": "Mid-Level Backend Engineer"}, "mid-level"),
        ({"title": "Intermediate Software Developer"}, "mid-level"),
        ({"title": "Senior Python Engineer"}, "senior"),
        ({"title": "Staff Software Engineer"}, "senior"),
        ({"title": "Principal Engineer"}, "senior"),
        ({"title": "Lead Engineer"}, "senior"),
    ],
)
def test_classifies_experience_level_from_job_title(job, expected):
    from app.services.job_relevance import classify_experience_level

    assert classify_experience_level(job) == expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("This is an entry-level role for a new graduate.", "entry-level"),
        ("This junior position is suitable for early-career developers.", "junior"),
        ("We are hiring for a mid-level role.", "mid-level"),
        ("This is a senior-level position.", "senior"),
    ],
)
def test_classifies_explicit_experience_level_from_description(
    description, expected
):
    from app.services.job_relevance import classify_experience_level

    assert classify_experience_level(
        {"title": "Software Engineer", "description": description}
    ) == expected


@pytest.mark.parametrize(
    "job",
    [
        {},
        {"title": "Software Engineer"},
        {"title": "Python Developer", "description": "Requires 3 years of experience."},
        {
            "title": "Python Developer",
            "description": "You will work with senior engineers.",
        },
        {
            "title": "Junior Python Developer",
            "description": "This is a senior-level position.",
        },
        {"title": "Associate Software Engineer"},
    ],
)
def test_returns_unknown_when_experience_level_is_not_clear(job):
    from app.services.job_relevance import classify_experience_level

    assert classify_experience_level(job) == "unknown"


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "Software Developer",
        "Graduate Software Engineer",
        "Junior Software Developer",
        "Associate Software Engineer",
    ],
)
def test_general_software_roles_match_software_engineering_family(title):
    result = score_job_relevance({"title": title})

    assert "Software engineering" in result["matched_role_families"]
    assert result["score"] >= 40


def test_unrelated_developer_role_does_not_match_software_engineering_family():
    result = score_job_relevance(
        {
            "title": "Business Development Manager",
            "description": "Build partnerships and manage client accounts.",
        }
    )

    assert "Software engineering" not in result["matched_role_families"]


@pytest.mark.parametrize(
    "title",
    [
        "QA Engineer - Backend (Golang)",
        "Junior Product Manager",
        "Graduate Talent Scientist",
        "Human Data Manager, New Grad",
        "Ubuntu Sales Engineer (Entry-Level)",
        "Quality Assurance Engineer",
    ],
)
def test_non_development_titles_do_not_match_software_role_families(title):
    result = score_job_relevance({
        "title": title,
        "description": (
            "We build software using Python, React, FastAPI, "
            "JavaScript, and modern web technologies."
        ),
    })

    assert result["matched_role_families"] == []


def test_software_engineer_cpp_title_still_matches():
    result = score_job_relevance({
        "title": "Junior Software Engineer - Cross-platform C++",
        "description": "Develop cross-platform applications.",
    })

    assert "Software engineering" in result["matched_role_families"]
