from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from typing import List

import json
import os
import zipfile
from datetime import datetime

from services.matcher import match_candidates
from services.cv_generator import generate_client_cv_json
from services.docx_generator import generate_docx
from services.comparison_service import compare_candidates
from services.jd_extractor import extract_jd_text
from services.faiss_service import rebuild_index_from_parsed_json


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
JD_UPLOAD_FOLDER = "uploads/jds"


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


@app.post(
    "/upload-jd",
    response_class=PlainTextResponse
)
async def upload_jd(
    file: UploadFile = File(...)
):

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="JD file is required"
        )

    os.makedirs(
        JD_UPLOAD_FOLDER,
        exist_ok=True
    )

    safe_filename = os.path.basename(
        file.filename
    )

    file_path = os.path.join(
        JD_UPLOAD_FOLDER,
        safe_filename
    )

    content = await file.read()

    if not content:

        raise HTTPException(
            status_code=400,
            detail="JD file is empty"
        )

    with open(
        file_path,
        "wb"
    ) as f:

        f.write(
            content
        )

    try:

        return extract_jd_text(
            file_path
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    finally:

        if os.path.exists(
            file_path
        ):
            os.remove(
                file_path
            )


@app.post("/compare-candidates")
def compare_selected_candidates(
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

    comparison = compare_candidates(
        candidate_names,
        jd_text,
        PARSED_JSON_FOLDER
    )

    if not comparison["results"]:

        raise HTTPException(
            status_code=404,
            detail="No matching candidates found"
        )

    return comparison


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

        template_path = "uploads/templates/active_template.docx"
        if not os.path.exists(template_path):
            template_path = None

        generate_docx(
            cv_json,
            docx_path,
            template_path=template_path
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


def find_matched_candidate(new_cand, parsed_json_folder):
    import re
    
    def normalize_name(name):
        if not name:
            return ""
        name = name.lower().strip()
        name = name.replace(".", "")
        name = re.sub(r'\s+', ' ', name)
        return name

    def normalize_phone(phone):
        if not phone:
            return ""
        return re.sub(r'\D', '', phone)

    new_email = new_cand.get("email", "").strip().lower()
    new_phone = normalize_phone(new_cand.get("phone", ""))
    new_name_norm = normalize_name(new_cand.get("candidate_name", ""))

    if not os.path.exists(parsed_json_folder):
        return None, None

    for filename in os.listdir(parsed_json_folder):
        if not filename.endswith(".json") or filename == "upload_stats.json":
            continue
        file_path = os.path.join(parsed_json_folder, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                exist_cand = json.load(f)
            
            exist_email = exist_cand.get("email", "").strip().lower()
            exist_phone = normalize_phone(exist_cand.get("phone", ""))
            exist_name_norm = normalize_name(exist_cand.get("candidate_name", ""))
            
            # 1. Email Match (highest priority)
            if new_email and exist_email and new_email == exist_email:
                return filename, exist_cand.get("candidate_name")
                
            # 2. Phone Match (only if email is missing on either)
            if (not new_email or not exist_email) and new_phone and exist_phone and new_phone == exist_phone:
                return filename, exist_cand.get("candidate_name")
                
            # 3. Normalized Name Match (only if BOTH email and phone are unavailable on BOTH)
            if (not new_email and not new_phone) and (not exist_email and not exist_phone) and new_name_norm and exist_name_norm and new_name_norm == exist_name_norm:
                return filename, exist_cand.get("candidate_name")
        except Exception:
            pass
            
    return None, None


@app.post("/upload-resumes")
async def upload_resumes(
    files: List[UploadFile] = File(...)
):
    os.makedirs(PARSED_JSON_FOLDER, exist_ok=True)
    temp_dir = "uploads/temp"
    os.makedirs(temp_dir, exist_ok=True)

    uploaded_candidates = []
    failed_uploads = []

    stats_path = "embeddings/upload_stats.json"
    stats = {"new_candidates": 0, "updated_candidates": 0}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r") as f:
                stats = json.load(f)
        except Exception:
            pass

    cache_path = "embeddings/candidate_embeddings.json"
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cache = json.load(f)
        except Exception:
            pass

    cache_modified = False
    from services.parser import parse_resume

    for file in files:
        if not file.filename:
            continue

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".pdf", ".docx"]:
            failed_uploads.append({
                "filename": file.filename,
                "error": "Unsupported file format. Only PDF and DOCX are allowed."
            })
            continue

        temp_file_path = os.path.join(temp_dir, file.filename)
        try:
            content = await file.read()
            with open(temp_file_path, "wb") as f:
                f.write(content)

            candidate = parse_resume(temp_file_path)
            candidate_name = candidate.get("candidate_name", "Unknown_Candidate")

            safe_filename = (
                candidate_name
                .replace("/", "_")
                .replace("\\", "_")
                .replace(":", "_")
            )

            # Check for duplicate candidate using robust rules
            matched_filename, matched_candidate_name = find_matched_candidate(candidate, PARSED_JSON_FOLDER)
            
            if matched_filename:
                is_update = True
                json_file_path = os.path.join(PARSED_JSON_FOLDER, matched_filename)
            else:
                is_update = False
                base_filename = safe_filename
                counter = 0
                while True:
                    cand_file = f"{base_filename}.json" if counter == 0 else f"{base_filename}_{counter}.json"
                    json_file_path = os.path.join(PARSED_JSON_FOLDER, cand_file)
                    if not os.path.exists(json_file_path):
                        break
                    counter += 1

            with open(json_file_path, "w", encoding="utf-8") as f_out:
                json.dump(candidate, f_out, indent=4, ensure_ascii=False)

            if is_update:
                stats["updated_candidates"] += 1
            else:
                stats["new_candidates"] += 1

            if candidate_name in cache:
                del cache[candidate_name]
                cache_modified = True

            if matched_candidate_name and matched_candidate_name in cache:
                del cache[matched_candidate_name]
                cache_modified = True

            if matched_filename and matched_filename in cache:
                del cache[matched_filename]
                cache_modified = True

            new_filename = os.path.basename(json_file_path)
            if new_filename in cache:
                del cache[new_filename]
                cache_modified = True

            uploaded_candidates.append({
                "filename": file.filename,
                "candidate_name": candidate_name,
                "status": "processed"
            })

        except Exception as e:
            failed_uploads.append({
                "filename": file.filename,
                "error": str(e)
            })
        finally:
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass

    if cache_modified:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(cache, f, indent=4)
        except Exception:
            pass

    try:
        rebuild_index_from_parsed_json(PARSED_JSON_FOLDER)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rebuild index: {str(e)}"
        )

    try:
        if os.path.exists(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
    except Exception:
        pass

    try:
        os.makedirs(os.path.dirname(stats_path), exist_ok=True)
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=4)
    except Exception:
        pass

    return {
        "status": "success",
        "uploaded": uploaded_candidates,
        "failed": failed_uploads,
        "total_successful": len(uploaded_candidates),
        "total_failed": len(failed_uploads),
        "new_candidates": stats["new_candidates"],
        "updated_candidates": stats["updated_candidates"]
    }


@app.get("/upload-stats")
def get_upload_stats():
    stats_path = "embeddings/upload_stats.json"
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"new_candidates": 0, "updated_candidates": 0}


@app.post("/reset-upload-stats")
def reset_upload_stats():
    stats_path = "embeddings/upload_stats.json"
    stats = {"new_candidates": 0, "updated_candidates": 0}
    try:
        os.makedirs(os.path.dirname(stats_path), exist_ok=True)
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset upload stats: {str(e)}"
        )

    # Count total indexed candidates
    total_indexed = 0
    if os.path.exists(PARSED_JSON_FOLDER):
        for filename in os.listdir(PARSED_JSON_FOLDER):
            if filename.endswith(".json") and filename != "upload_stats.json":
                total_indexed += 1

    return {
        "message": "Upload statistics reset successfully.",
        "total_indexed": total_indexed,
        "new_candidates": 0,
        "updated_candidates": 0
    }


TEMPLATE_FOLDER = "uploads/templates"
TEMPLATE_PATH = os.path.join(TEMPLATE_FOLDER, "active_template.docx")
TEMPLATE_METADATA_PATH = os.path.join(TEMPLATE_FOLDER, "metadata.json")


@app.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Template file is required"
        )

    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".docx":
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only DOCX templates are supported."
        )

    os.makedirs(TEMPLATE_FOLDER, exist_ok=True)

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty"
        )

    with open(TEMPLATE_PATH, "wb") as f:
        f.write(content)

    metadata = {
        "filename": file.filename,
        "uploaded_at": datetime.now().isoformat()
    }

    with open(TEMPLATE_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    return {
        "status": "success",
        "message": "Template uploaded successfully",
        "filename": file.filename
    }


@app.get("/active-template")
def get_active_template():
    if os.path.exists(TEMPLATE_PATH) and os.path.exists(TEMPLATE_METADATA_PATH):
        try:
            with open(TEMPLATE_METADATA_PATH, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            return {
                "active": True,
                "filename": metadata.get("filename"),
                "uploaded_at": metadata.get("uploaded_at")
            }
        except Exception:
            return {
                "active": True,
                "filename": "active_template.docx",
                "uploaded_at": None
            }
    return {
        "active": False,
        "filename": None
    }


@app.delete("/active-template")
def delete_active_template():
    if os.path.exists(TEMPLATE_PATH):
        try:
            os.remove(TEMPLATE_PATH)
        except Exception:
            pass
    if os.path.exists(TEMPLATE_METADATA_PATH):
        try:
            os.remove(TEMPLATE_METADATA_PATH)
        except Exception:
            pass
    return {
        "status": "success",
        "message": "Template deleted successfully, reverted to default style."
    }


# Mount the recruiter dashboard frontend
os.makedirs("frontend", exist_ok=True)
app.mount("/dashboard", StaticFiles(directory="frontend", html=True), name="dashboard")
