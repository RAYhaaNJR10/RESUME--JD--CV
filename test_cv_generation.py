from services.parser import parse_resume
from services.cv_generator import (
    generate_client_cv_json
)

candidate = parse_resume(
    "uploads/resumes/Kollu Pavani_Autosys.docx"
)

jd = """
Production Support Engineer

Autosys
Control-M
CAWA
TWS
Unix
Linux
Shell Scripting

Incident Management
Problem Management
Batch Monitoring
Production Support
ITIL
"""

result = generate_client_cv_json(
    candidate,
    jd
)

print(result)