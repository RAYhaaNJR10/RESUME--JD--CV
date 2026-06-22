import os
import json

from services.parser import parse_resume
from services.embedding_service import create_embedding
from services.faiss_service import add_candidate


RESUME_FOLDER = "uploads/resumes"
PARSED_JSON_FOLDER = "parsed_json"


os.makedirs(
    PARSED_JSON_FOLDER,
    exist_ok=True
)


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
        candidate.get(
            "resume_filename"
        )
    )

    # ==========================
    # Save Parsed JSON
    # ==========================

    candidate_name = candidate.get(
        "candidate_name",
        "Unknown_Candidate"
    )

    safe_filename = (
        candidate_name
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )

    json_file_path = os.path.join(
        PARSED_JSON_FOLDER,
        f"{safe_filename}.json"
    )

    with open(
        json_file_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            candidate,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(
        f"Saved JSON -> {json_file_path}"
    )

    # ==========================
    # Create Embedding
    # ==========================

    embedding = create_embedding(
        candidate["search_profile"]
    )

    add_candidate(
        candidate,
        embedding
    )

print(
    "\nIndex Build Complete"
)