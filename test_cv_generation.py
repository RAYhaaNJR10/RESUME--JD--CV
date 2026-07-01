from services.parser import parse_resume
from services.cv_generator import (
    generate_client_cv_json
)

candidate = parse_resume(
    "uploads/resumes/Aditya_Nair.docx"
)

jd = """
Python Developer

Required Skills:
- Python
- MySQL
- Git
- Good communication and teamwork
"""

result = generate_client_cv_json(
    candidate,
    jd
)

print(result)