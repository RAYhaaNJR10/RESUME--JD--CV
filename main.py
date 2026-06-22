from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import json
import os
import zipfile

from services.matcher import match_candidates
from services.cv_generator import generate_client_cv_json
from services.docx_generator import generate_docx


app = FastAPI(
    title="Resume JD CV Platform"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PARSED_JSON_FOLDER = "parsed_json"
GENERATED_CVS_FOLDER = "generated_cvs"


@app.get("/")
def home():

    return {
        "message": "Resume JD CV Platform Running"
    }


@app.post("/rank-candidates")
def rank_candidates(
    payload: dict
):

    jd_text = payload.get(
        "jd",
        ""
    )

    if not jd_text:

        raise HTTPException(
            status_code=400,
            detail="JD text is required"
        )

    results = match_candidates(
        jd_text,
        top_k=100
    )

    return {
        "count": len(results),
        "results": results
    }


@app.get("/candidates")
def get_all_candidates():

    candidates = []

    if not os.path.exists(
        PARSED_JSON_FOLDER
    ):
        return []

    for filename in os.listdir(
        PARSED_JSON_FOLDER
    ):

        if not filename.endswith(".json"):
            continue

        file_path = os.path.join(
            PARSED_JSON_FOLDER,
            filename
        )

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                candidate = json.load(f)

            candidates.append(
                {
                    "candidate_name":
                        candidate.get(
                            "candidate_name",
                            ""
                        ),

                    "current_role":
                        candidate.get(
                            "current_role",
                            ""
                        ),

                    "years_of_experience":
                        candidate.get(
                            "years_of_experience",
                            0
                        ),

                    "filename":
                        filename
                }
            )

        except Exception:
            pass

    return candidates


@app.get("/candidate/{candidate_name}")
def get_candidate_details(
    candidate_name: str
):

    file_path = os.path.join(
        PARSED_JSON_FOLDER,
        f"{candidate_name}.json"
    )

    if not os.path.exists(
        file_path
    ):

        raise HTTPException(
            status_code=404,
            detail="Candidate not found"
        )

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as f:

        candidate = json.load(f)

    return candidate


@app.post("/generate-selected-cvs")
def generate_selected_cvs(
    payload: dict
):

    candidate_names = payload.get(
        "candidate_names",
        []
    )

    jd_text = payload.get(
        "jd",
        ""
    )

    if not candidate_names:

        raise HTTPException(
            status_code=400,
            detail="No candidates selected"
        )

    if not jd_text:

        raise HTTPException(
            status_code=400,
            detail="JD text is required"
        )

    os.makedirs(
        GENERATED_CVS_FOLDER,
        exist_ok=True
    )

    generated_files = []

    for candidate_name in candidate_names:

        json_path = os.path.join(
            PARSED_JSON_FOLDER,
            f"{candidate_name}.json"
        )

        if not os.path.exists(
            json_path
        ):
            continue

        with open(
            json_path,
            "r",
            encoding="utf-8"
        ) as f:

            candidate_json = json.load(f)

        cv_json = generate_client_cv_json(
            candidate_json,
            jd_text
        )

        docx_path = os.path.join(
            GENERATED_CVS_FOLDER,
            f"{candidate_name}.docx"
        )

        generate_docx(
            cv_json,
            docx_path
        )

        generated_files.append(
            docx_path
        )

    if not generated_files:

        raise HTTPException(
            status_code=404,
            detail="No CVs generated"
        )

    zip_path = os.path.join(
        GENERATED_CVS_FOLDER,
        "selected_cvs.zip"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as zipf:

        for file in generated_files:

            zipf.write(
                file,
                arcname=os.path.basename(
                    file
                )
            )

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="selected_cvs.zip"
    )