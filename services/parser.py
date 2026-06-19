import os
import json

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

    return data