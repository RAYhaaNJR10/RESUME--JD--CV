import json

from services.parser import parse_resume
from services.embedding_service import create_embedding

data = parse_resume(
    "uploads/resumes/Adarsh_CV.pdf"
)

embedding = create_embedding(
    data["search_profile"]
)

print(len(embedding))