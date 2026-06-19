import os

from services.parser import parse_resume
from services.embedding_service import create_embedding
from services.faiss_service import add_candidate


RESUME_FOLDER = "uploads/resumes"


for filename in os.listdir(
    RESUME_FOLDER
):

    file_path = os.path.join(
        RESUME_FOLDER,
        filename
    )

    print(
        f"Processing {filename}"
    )

    candidate = parse_resume(
        file_path
    )

    print(
        "Resume filename:",
        candidate.get("resume_filename")
    )

    embedding = create_embedding(
        candidate["search_profile"]
    )

    add_candidate(
        candidate,
        embedding
    )

print("Done")