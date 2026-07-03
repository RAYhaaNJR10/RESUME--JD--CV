import os
import json

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def generate_client_cv_json(
    candidate_json,
    jd_text
):

    prompt = f"""
You are an expert recruitment consultant.

Your task is to create a professional client-facing CV profile.

IMPORTANT RULES:

1. Use ONLY information present in the candidate profile.

2. Do NOT invent:
   - experience
   - projects
   - skills
   - education
   - certifications
   - awards

3. Never generate:
   - N/A
   - Not Available
   - Not Mentioned

4. Do NOT create empty sections.

5. Keep each project separate.

6. Do NOT merge projects.

7. Focus heavily on information relevant to the Job Description.

8. Return ONLY valid JSON.

9. This is a CLIENT-FACING CV.

10. Prioritize business value and outcomes over technical implementation details.

OUTPUT SCHEMA:

{{
    "candidate_name": "",

    "current_role_title": "",

    "about_candidate": "",

    "strengths": [
        {{
            "strength": "",
            "score": 1,
            "assessment": ""
        }}
    ],

    "professional_experience": [
        {{
            "company": "",
            "project": "",
            "role": "",
            "role_summary": "",
            "key_achievements": []
        }}
    ],

    "technical_skills": [
        {{
            "technology_area": "",
            "skills": []
        }}
    ],

    "education": [
        {{
            "degree": "",
            "institution": "",
            "start_year": "",
            "end_year": ""
        }}
    ]
}}

ABOUT_CANDIDATE:

- 4 to 6 recruiter-facing lines.
- Mention years of experience.
- Mention domain expertise.
- Mention major technologies.
- Mention business impact.
- Align to the Job Description.

STRENGTHS:

Return EXACTLY 5 strengths.

Format:

[
    {{
        "strength": "",
        "score": 1,
        "assessment": ""
    }}
]

Rules:

- Strengths must be capabilities, not technologies.
- Do NOT use AWS, Python, SQL, Linux etc as strengths.
- Score each capability dynamically (1-5) using these guidelines:
  5 = Strong evidence demonstrated consistently across multiple roles, projects, and responsibilities.
  4 = Good practical experience with clear supporting evidence.
  3 = Moderate exposure or working knowledge.
  2 = Limited experience or brief mention.
  1 = Minimal or no supporting evidence.
- The scores should evaluate each strength independently based on actual resume content; do NOT follow a fixed template pattern (like 5, 5, 5, 4, 4).
- The "assessment" must briefly explain why the candidate received that score using evidence from the resume (e.g. referencing years of experience, specific roles, tasks or projects).
- Do NOT invent experience or achievements, and do NOT write generic statements. Every assessment must be unique and logically aligned with the score.

Examples:

- Production Support Operations
- Root Cause Analysis
- Incident & Problem Management
- Data Engineering Architecture
- Cloud Platform Engineering
- ETL Pipeline Development
- Performance Optimization
- Stakeholder Communication
- Data Governance
- Application Support
- Service Management

PROFESSIONAL_EXPERIENCE:

- Keep every project separate.
- Never merge projects.
- Role Summary must be 3-4 concise recruiter-facing sentences.
- Focus on:
    - Business objective
    - Business problem solved
    - Solution delivered
    - Business outcome

PROJECT DIFFERENTIATION RULES:

If multiple projects contain similar technologies:

- Keep all projects separate.
- Avoid repeating the same technology description.
- Focus on different business outcomes.
- Focus on stakeholders, reporting, compliance, analytics, operations and business value.

KEY ACHIEVEMENTS:

- Maximum 5 bullets per project.
- Focus on business impact first.
- Avoid low-level implementation details.
- Use concise recruiter-friendly language.

TECHNICAL SKILLS:

Return as technology areas.

Rules:

- Maximum 8 categories.
- Maximum 8 skills per category.
- Only include strongest and most relevant skills.

Preferred Categories:

- Cloud Platforms
- Data Engineering
- Big Data Technologies
- Database Technologies
- Programming Languages
- Governance & Security
- CI/CD Tools
- Analytics & Reporting
- Monitoring & Support
- Scheduling & Automation

Do NOT create:

- Business Domains
- Domain Knowledge
- Industry Experience
- Functional Areas

Domain knowledge belongs in:

- About Candidate
- Professional Experience

EDUCATION:

- Return actual education only.
- Return highest completed degree only.
- Do not include:
    - High School
    - Intermediate
    - Secondary School
    - 10th Grade
    - 12th Grade

unless no higher education exists.

JOB DESCRIPTION:

{jd_text}

CANDIDATE PROFILE:

{json.dumps(candidate_json, indent=2)}
"""

    model_name = os.getenv("OPENAI_MODEL", "gpt-5.5")
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = response.choices[0].message.content.strip()

    if content.startswith("```json"):
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

    try:
        return json.loads(content)

    except Exception as e:

        print("CV JSON Parse Error:", e)
        print(content)

        raise Exception(
            "Failed to parse generated CV JSON"
        )