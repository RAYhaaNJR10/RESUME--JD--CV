import os
import json
import re

from services.extractor import extract_text
from services.openai_service import parse_resume_with_ai


def parse_resume(file_path):
    resume_text = extract_text(file_path)

    parsed_json = parse_resume_with_ai(
        resume_text
    )

    data = json.loads(parsed_json)

    data["resume_filename"] = os.path.basename(
        file_path
    )

    # Extract email using regex if not already present
    if "email" not in data or not data["email"]:
        email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        emails = re.findall(email_pattern, resume_text)
        data["email"] = emails[0].strip().lower() if emails else ""

    # Extract phone using regex if not already present
    if "phone" not in data or not data["phone"]:
        phone_pattern = r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+?\d{10,12}'
        phones = re.findall(phone_pattern, resume_text)
        phone_val = ""
        if phones:
            cleaned = re.sub(r'\D', '', phones[0])
            if len(cleaned) >= 10:
                phone_val = cleaned
        data["phone"] = phone_val

    return data
