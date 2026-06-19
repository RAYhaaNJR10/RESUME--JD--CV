from services.embedding_service import create_embedding
from services.faiss_service import search_candidates


jd = """
Experience with IBM Sterling Suite.
Experience with AWS (EC2, S3, EFS, RDS, IAM).
Experience with CI/CD workflows (We use Cloudbees as our pipeline tool).
Experience with Terraform and Ansible.
"""

jd_embedding = create_embedding(jd)

results = search_candidates(
    jd_embedding,
    top_k=10
)

print("\nRESULTS:\n")

for candidate in results:

    print(
        candidate["candidate_name"],
        round(candidate["score"], 4),
        candidate["current_role"]
    )