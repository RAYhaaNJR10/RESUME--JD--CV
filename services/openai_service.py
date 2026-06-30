import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def parse_resume_with_ai(resume_text):

    prompt = f"""
You are an expert resume parser.

Extract information from the resume.

Return ONLY valid JSON.

Do not explain anything.
Do not wrap JSON in markdown.
Do not invent information.

If information is missing:
- Use empty strings
- Use empty arrays
- Use 0 for years_of_experience

IMPORTANT RULES:

1. Extract ALL experience entries separately.
2. Do NOT merge multiple experiences into one.
3. If a resume contains 5 experiences, return 5 experience objects.
4. Extract ALL projects separately.
5. Extract ALL skills mentioned anywhere in the resume.
6. Extract ALL domains if they can be inferred.
7. Generate a concise search_profile optimized for semantic matching.
8. The search_profile should contain:
   - Current role
   - Years of experience
   - Core skills
   - Technologies
   - Domains

Schema:

{{
  "candidate_name": "",
  "current_role": "",
  "years_of_experience": 0,

  "skills": [],

  "domains": [],

  "experience": [
    {{
      "company": "",
      "project": "",
      "role": "",
      "start_date": "",
      "end_date": "",
      "technologies": [],
      "responsibilities": []
    }}
  ],

  "education": [
    {{
      "degree": "",
      "institution": "",
      "start_year": "",
      "end_year": ""
    }}
  ],

  "projects": [
    {{
      "name": "",
      "description": "",
      "technologies": []
    }}
  ],

  "search_profile": ""
}}

Resume:

{resume_text}
"""

    model_name = os.getenv("OPENAI_MODEL", "gpt-5.5")
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    content = response.choices[0].message.content.strip()

    if content.startswith("```json"):
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

    return content