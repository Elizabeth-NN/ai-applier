from app.services.resume_job_matching import (
    build_requirement_term_evidence,
    build_term_weights,
    prepare_job_matching_text,
    prepare_resume_section_features,
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

def test_relevant_technical_role_beats_unrelated_role_with_generic_overlap():
    resume = (
        "Python backend developer. "
        "Built REST APIs using FastAPI and PostgreSQL. "
        "Used Docker to deploy web applications. "
        "Experienced in planning, communication, analysis, and management."
    )

    backend = score_resume_job_match(
        resume,
        title="Junior Python Backend Developer",
        description=(
            "Build REST APIs using Python, FastAPI, PostgreSQL, and Docker."
        ),
    )

    ux_research = score_resume_job_match(
        resume,
        title="UX/UI Researcher",
        description=(
            "Support research planning, data analysis, communication, "
            "information gathering, and management of research projects."
        ),
    )

    assert backend["match_score"] > ux_research["match_score"]


def test_generic_filler_does_not_dominate_matched_terms():
    result = score_resume_job_match(
        (
            "Python backend developer. "
            "Built APIs using FastAPI and PostgreSQL."
        ),
        title="Python Backend Developer",
        description=(
            "Use Python, FastAPI, and PostgreSQL. "
            "Develop basic skills and manage current information."
        ),
    )

    generic_terms = {"basic", "current", "information", "skills"}

    assert not generic_terms.intersection(result["matched_terms"])


def test_specific_required_skills_outweigh_generic_requirement_overlap():
    title = "Backend Developer"
    description = (
        "Required: Python, FastAPI, and PostgreSQL. "
        "Must have experience building REST APIs. "
        "Strong communication and teamwork are important."
    )

    technical_resume = (
        "Backend developer experienced with Python, FastAPI, "
        "PostgreSQL, and REST APIs."
    )

    generic_resume = (
        "Backend developer with strong communication skills "
        "and experience working in teams."
    )

    technical = score_resume_job_match(
        technical_resume,
        title=title,
        description=description,
    )
    generic = score_resume_job_match(
        generic_resume,
        title=title,
        description=description,
    )

    assert technical["match_score"] > generic["match_score"]


def test_punctuation_does_not_create_artificial_phrases():
    result = score_resume_job_match(
        "Python backend developer using FastAPI and PostgreSQL.",
        title="Junior Python Backend Developer",
        description="Required: Python, FastAPI, PostgreSQL, and Docker.",
    )

    assert "python fastapi postgresql" not in result["matched_terms"]
    assert "ux ui researcher" not in result["terms_not_found_in_resume"]
    assert "docker" in result["terms_not_found_in_resume"]


def test_all_comma_separated_required_skills_are_counted():
    result = score_resume_job_match(
        "Python developer using FastAPI, PostgreSQL, and Docker.",
        title="Backend Developer",
        description=(
            "Required: Python, FastAPI, PostgreSQL, and Docker."
        ),
    )

    assert "Explicit requirement term coverage: 100%." in result["match_reasons"]

def test_title_overlap_does_not_dominate_weak_description_match():
    result = score_resume_job_match(
        (
            "Business analyst with experience in business analysis, "
            "data reporting, project planning, and management."
        ),
        title="Business Analyst",
        description=(
            "Design and maintain distributed systems using Kubernetes, "
            "Terraform, Go, and cloud infrastructure."
        ),
    )

    assert result["match_score"] < 45


def test_required_and_preferred_skills_are_separated_in_mixed_sentence():
    from app.services.resume_job_matching import _requirement_classifications

    required, preferred = _requirement_classifications(
        "Python is required, while Docker is preferred."
    )

    assert "python" in required
    assert "docker" not in required
    assert "docker" in preferred
    assert "python" not in preferred


def test_requirement_and_preference_sections_are_separated():
    from app.services.resume_job_matching import _requirement_classifications

    required, preferred = _requirement_classifications(
        """
        Requirements:
        - Python
        - FastAPI

        Nice to have:
        - Docker
        - Kubernetes
        """
    )

    assert {"python", "fastapi"} <= required
    assert {"docker", "kubernetes"} <= preferred


def test_not_required_skill_is_not_classified_as_preferred():
    from app.services.resume_job_matching import _requirement_classifications

    required, preferred = _requirement_classifications(
        "Kubernetes is not required."
    )

    assert "kubernetes" not in required
    assert "kubernetes" not in preferred


def test_required_and_preferred_skills_are_separated_without_comma():
    from app.services.resume_job_matching import _requirement_classifications

    required, preferred = _requirement_classifications(
        "Python is required but Docker is preferred."
    )

    assert "python" in required
    assert "python" not in preferred
    assert "docker" in preferred
    assert "docker" not in required


def test_resume_section_features_are_prepared_independently():
    structured_resume = {
        "skills": [{"text": "Python, FastAPI, PostgreSQL"}],
        "experience": [{"text": "Built Python backend APIs"}],
        "projects": [{"text": "Created a React application"}],
        "education": [{"text": "Software Engineering"}],
        "certifications": [{"text": "AWS Cloud Practitioner"}],
        "summary": [{"text": "Backend developer using Python"}],
    }

    features = prepare_resume_section_features(structured_resume)

    assert "python" in features["skills"]
    assert "python" in features["experience"]
    assert "python" in features["summary"]
    assert "react" in features["projects"]
    assert "softwar engin" in features["education"]
    assert "aws" in features["certifications"]
    assert "react" not in features["skills"]


def test_requirement_evidence_identifies_all_matching_sections():
    structured_resume = {
        "skills": [{"text": "Python, NodeJS, FastAPI"}],
        "experience": [{"text": "Built Python APIs"}],
        "projects": [{"text": "Created a Node.js service using FastAPI"}],
        "education": [{"text": "Software Engineering"}],
        "certifications": [],
        "summary": [{"text": "Python backend developer"}],
    }

    section_features = prepare_resume_section_features(structured_resume)

    evidence = build_requirement_term_evidence(
        (
            "Required qualifications:\n"
            "- Python\n"
            "- Node.js\n"
            "- FastAPI\n"
            "- Kubernetes"
        ),
        section_features,
    )

    assert evidence["python"] == ["skills", "experience", "summary"]
    assert evidence["node.js"] == ["skills", "projects"]
    assert evidence["fastapi"] == ["skills", "projects"]
    assert evidence["kubernetes"] == []



def test_matching_excludes_urls_emails_and_multiword_company_names():
    result = score_resume_job_match(
        "Python developer building backend APIs.",
        title="Example Tech Python Developer",
        description=(
            "Example Tech is hiring. "
            "Apply at https://example.com/jobs. "
            "Contact recruiter@example.com. "
            "Requirements: Python and FastAPI."
        ),
        company="Example Tech",
    )

    combined_terms = (
        result["matched_terms"] + result["terms_not_found_in_resume"]
    )
    combined_text = " ".join(combined_terms).lower()

    assert "python" in result["matched_terms"]
    assert "example" not in combined_text
    assert "tech" not in combined_text
    assert "recruiter" not in combined_text
    assert "example.com" not in combined_text
    assert "fastapi" in result["terms_not_found_in_resume"]


def test_single_word_company_name_does_not_remove_a_technical_skill():
    result = score_resume_job_match(
        "Built backend services using Go.",
        title="Go Developer",
        description="Build Go services and APIs.",
        company="Go",
    )

    assert "go" in result["matched_terms"]


def test_requirement_evidence_excludes_multiword_company_name():
    evidence = build_requirement_term_evidence(
        (
            "Example Tech is hiring. "
            "Apply at https://example.com/jobs.\n"
            "Requirements:\n"
            "Python and FastAPI."
        ),
        {"skills": frozenset({"python"})},
        company="Example Tech",
    )

    assert "python" in evidence
    assert "fastapi" in evidence
    assert "example" not in evidence
    assert "tech" not in evidence


def test_corpus_matching_text_excludes_contact_and_company_noise():
    cleaned = prepare_job_matching_text(
        "Example Tech Python Developer",
        (
            "Apply at https://example.com/jobs. "
            "Email recruiter@example.com. "
            "Requirements: Python and FastAPI."
        ),
        company="Example Tech",
    )

    weights = build_term_weights([cleaned])

    assert "python" in weights
    assert "fastapi" in weights
    assert "example" not in weights
    assert "tech" not in weights
    assert "recruiter" not in weights
