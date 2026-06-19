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

3. Never generate placeholders.

4. Never generate:
   - N/A
   - Not Available
   - Not Mentioned

5. Do NOT create empty sections.

6. If a section has no data, omit it completely.

7. If a candidate has only 2 experiences,
   return only 2 experiences.

8. Keep each project/engagement as a separate professional experience.

9. Do NOT merge experiences even if:
   - company is the same
   - role is the same
   - technologies are similar

10. Preserve project-level granularity.

11. If candidate has 6 projects,
    return 6 professional_experience entries.

12. If candidate has 2 projects,
    return 2 professional_experience entries.

13. Do not create empty experience sections.

14. Avoid repeating identical achievements across experiences where possible,
    but keep experiences separate.

15. Focus on information relevant to the Job Description.

16. Write concise recruiter-friendly content.

17. Technical skills must be grouped into categories.

18. Return ONLY valid JSON.

OUTPUT SCHEMA:

{{
    "candidate_name": "",

    "about_candidate": "",

    "strengths": [],

    "professional_experience": [
        {{
            "company": "",
            "project": "",
            "role": "",
            "role_summary": "",
            "key_achievements": []
        }}
    ],

    "technical_skills": {{
        "Cloud": [],
        "Data Engineering": [],
        "Programming": [],
        "Databases": [],
        "DevOps": [],
        "Analytics": [],
        "Other": []
    }},

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

- 4 to 8 lines
- Professional summary
- Highlight years of experience
- Highlight relevant technologies
- Highlight domain expertise
- Align to the JD

STRENGTHS:

- 5 to 8 bullet points
- Most relevant strengths only

PROFESSIONAL_EXPERIENCE:

- Keep each project as a separate experience entry.
- Do not merge projects.
- Each experience must contain:
    - company
    - project
    - role
    - role_summary
    - key_achievements

- Focus on business impact.
- Focus on technologies relevant to the JD.
- Summarize lengthy responsibilities into concise achievements.

TECHNICAL_SKILLS RULES:

- Include only skills relevant to the JD.
- Remove redundant skills.

Maximum skills per category:

- Cloud: 8
- Data Engineering: 10
- Programming: 5
- Databases: 5
- DevOps: 5
- Analytics: 5
- Other: 5

Group skills logically.

Example:

"Cloud": [
    "AWS",
    "Azure"
]

"Programming": [
    "Python",
    "SQL"
]

Do not dump all skills into one list.

JOB DESCRIPTION:

{jd_text}

CANDIDATE PROFILE:

{json.dumps(candidate_json, indent=2)}
"""

    response = client.chat.completions.create(
        model="gpt-5.5",
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

    return content