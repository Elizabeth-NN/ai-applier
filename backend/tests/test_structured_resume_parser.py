from app.services.structured_resume_parser import parse_resume_text


def test_parses_common_resume_sections_and_contact_details():
    text = """
    Jane Example
    jane@example.com
    +254 712 345 678
    https://github.com/jane

    PROFESSIONAL SUMMARY
    Python developer building backend APIs.

    TECHNICAL SKILLS
    Python
    FastAPI
    PostgreSQL

    PROFESSIONAL EXPERIENCE
    Backend Intern | Example Ltd | Jan 2025 - Jun 2025
    Built APIs using Python.

    PROJECTS
    Job Tracker
    Built with FastAPI and React.

    EDUCATION
    BSc Software Engineering | Example University

    CERTIFICATIONS
    AWS Cloud Practitioner
    """

    result = parse_resume_text(text)

    assert result["summary"] == [
        {"text": "Python developer building backend APIs."}
    ]
    assert result["skills"] == [
        {"text": "Python"},
        {"text": "FastAPI"},
        {"text": "PostgreSQL"},
    ]
    assert result["experience"] == [
        {"text": "Backend Intern | Example Ltd | Jan 2025 - Jun 2025"},
        {"text": "Built APIs using Python."},
    ]
    assert result["projects"] == [
        {"text": "Job Tracker"},
        {"text": "Built with FastAPI and React."},
    ]
    assert result["education"] == [
        {"text": "BSc Software Engineering | Example University"}
    ]
    assert result["certifications"] == [
        {"text": "AWS Cloud Practitioner"}
    ]

    assert result["contact"]["emails"] == ["jane@example.com"]
    assert result["contact"]["phone_numbers"] == ["+254 712 345 678"]
    assert result["contact"]["links"] == ["https://github.com/jane"]


def test_recognizes_case_insensitive_headings_and_inline_content():
    result = parse_resume_text(
        """
        professional summary: Backend developer.
        technical skills: Python, SQL, FastAPI
        """
    )

    assert result["summary"] == [
        {"text": "Backend developer."}
    ]
    assert result["skills"] == [
        {"text": "Python, SQL, FastAPI"}
    ]


def test_routes_unmodeled_sections_to_other():
    result = parse_resume_text(
        """
        PROFESSIONAL EXPERIENCE
        Backend Intern at Example Ltd.

        AWARDS
        Best Student Project.

        LANGUAGES
        English and Swahili.

        REFERENCES
        Available on request.

        EDUCATION
        BSc Software Engineering.
        """
    )

    assert result["experience"] == [
        {"text": "Backend Intern at Example Ltd."}
    ]
    assert result["education"] == [
        {"text": "BSc Software Engineering."}
    ]
    assert result["other"] == [
        {"text": "Best Student Project."},
        {"text": "English and Swahili."},
        {"text": "Available on request."},
    ]


def test_preserves_text_before_the_first_section():
    result = parse_resume_text(
        """
        Jane Example
        Nairobi, Kenya

        SKILLS
        Python
        """
    )

    assert result["other"] == [
        {"text": "Jane Example"},
        {"text": "Nairobi, Kenya"},
    ]
    assert result["skills"] == [{"text": "Python"}]


def test_repeated_section_headings_append_entries():
    result = parse_resume_text(
        """
        SKILLS
        Python

        EDUCATION
        BSc Computer Science

        SKILLS
        FastAPI
        """
    )

    assert result["skills"] == [
        {"text": "Python"},
        {"text": "FastAPI"},
    ]


def test_empty_resume_returns_consistent_structure():
    result = parse_resume_text("")

    expected_sections = (
        "summary",
        "skills",
        "experience",
        "projects",
        "education",
        "certifications",
        "other",
    )

    for section in expected_sections:
        assert result[section] == []

    assert result["contact"] == {
        "emails": [],
        "phone_numbers": [],
        "links": [],
    }
    assert result["original_text"] == ""


def test_preserves_original_extracted_text():
    text = "Jane Example\n\nSKILLS\nPython"

    result = parse_resume_text(text)

    assert result["original_text"] == text
