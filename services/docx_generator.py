# services/docx_generator.py

import os
from docx import Document


def generate_docx(cv_json, output_path):

    document = Document()

    # ==========================================
    # Candidate Details
    # ==========================================

    document.add_heading("Candidate Details", level=1)

    document.add_paragraph(
        f"Candidate Full Name: {cv_json.get('candidate_name', '')}"
    )

    role = ""

    experiences = cv_json.get(
        "professional_experience",
        []
    )

    if experiences:
        role = experiences[0].get(
            "role",
            ""
        )

    document.add_paragraph(
        f"Current Role: {role}"
    )

    # ==========================================
    # About Candidate
    # ==========================================

    about = cv_json.get(
        "about_candidate"
    )

    if about:

        document.add_heading(
            "About the Candidate",
            level=1
        )

        document.add_paragraph(
            about
        )

    # ==========================================
    # Strengths
    # ==========================================

    strengths = cv_json.get(
        "strengths",
        []
    )

    if strengths:

        document.add_heading(
            "Strengths",
            level=1
        )

        for strength in strengths:

            document.add_paragraph(
                strength,
                style="List Bullet"
            )

    # ==========================================
    # Professional Experience
    # ==========================================

    experiences = cv_json.get(
        "professional_experience",
        []
    )

    for idx, exp in enumerate(
        experiences,
        start=1
    ):

        document.add_heading(
            f"Experience Part {idx}",
            level=1
        )

        document.add_paragraph(
            f"Company: {exp.get('company', '')}"
        )

        document.add_paragraph(
            f"Project Name: {exp.get('project', '')}"
        )

        document.add_paragraph(
            f"Role: {exp.get('role', '')}"
        )

        document.add_paragraph(
            f"Role Summary: {exp.get('role_summary', '')}"
        )

        achievements = exp.get(
            "key_achievements",
            []
        )

        if achievements:

            document.add_paragraph(
                "Key Achievements:"
            )

            for achievement in achievements:

                document.add_paragraph(
                    achievement,
                    style="List Bullet"
                )

    # ==========================================
    # Technical Skills
    # ==========================================

    technical_skills = cv_json.get(
        "technical_skills",
        {}
    )

    if technical_skills:

        document.add_heading(
            "Technical Skills",
            level=1
        )

        for category, skills in technical_skills.items():

            if not skills:
                continue

            document.add_paragraph(
                f"{category}:"
            )

            document.add_paragraph(
                ", ".join(skills)
            )

    # ==========================================
    # Education
    # ==========================================

    education = cv_json.get(
        "education",
        []
    )

    if education:

        document.add_heading(
            "Education",
            level=1
        )

        for edu in education:

            document.add_paragraph(
                f"{edu.get('degree', '')}"
            )

            document.add_paragraph(
                f"{edu.get('institution', '')}"
            )

            start_year = edu.get(
                "start_year",
                ""
            )

            end_year = edu.get(
                "end_year",
                ""
            )

            if start_year or end_year:

                document.add_paragraph(
                    f"{start_year} - {end_year}"
                )

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )

    document.save(
        output_path
    )

    return output_path