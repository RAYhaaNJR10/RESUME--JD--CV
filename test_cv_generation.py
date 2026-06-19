from services.parser import parse_resume
from services.cv_generator import (
    generate_client_cv_json
)

candidate = parse_resume(
    "uploads/resumes/Adarsh_CV.pdf"
)

jd = """
Senior AWS Engineer

AWS Glue
Athena
Iceberg
PySpark
Data Lakehouse
Kinesis
Lambda
"""

result = generate_client_cv_json(
    candidate,
    jd
)

print(result)