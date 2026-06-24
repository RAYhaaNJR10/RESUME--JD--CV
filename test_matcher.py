# test_matcher.py

from services.matcher import (
    match_candidates
)

jd = """
Senior AWS Engineer

AWS Glue
AWS Lambda
AWS Athena
PySpark
Apache Iceberg
Kinesis
Data Lakehouse
"""

results = match_candidates(
    jd
)

print("\nRESULTS:\n")

for candidate in results:

    print(
        candidate["candidate_name"],
        round(candidate["score"], 4),
        candidate["current_role"]
    )