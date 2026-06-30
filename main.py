from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from typing import List
from concurrent.futures import ThreadPoolExecutor

import json
import os
import zipfile
import hashlib

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

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/dashboard", StaticFiles(directory=frontend_dir, html=True), name="dashboard")

try:
    from db import Base, engine, SessionLocal, CandidateModel, db_session_lock, get_next_employee_id, extract_email, extract_phone, save_generated_cv_to_db, normalize_candidate_name
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized successfully.")
except Exception as e:
    print(f"Database initialization failed: {e}")


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

        if not filename.endswith(".json") or filename == "upload_stats.json":
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
                        candidate.get("resume_filename", filename)
                }
            )

        except Exception:
            pass

    return candidates


@app.delete("/candidates")
def clear_all_candidates():
    from services.faiss_service import rebuild_index_from_json

    # 1. Clear database candidates table
    db = SessionLocal()
    try:
        with db_session_lock:
            db.query(CandidateModel).delete()
            db.commit()
    except Exception as dbe:
        print(f"Error clearing database candidates: {dbe}")
    finally:
        db.close()

    # 2. Clear parsed JSON folder
    if os.path.exists(PARSED_JSON_FOLDER):
        for filename in os.listdir(PARSED_JSON_FOLDER):
            if filename.endswith(".json"):
                try:
                    os.remove(os.path.join(PARSED_JSON_FOLDER, filename))
                except Exception:
                    pass

    # 3. Clear uploads/resumes files (keeping cache folder)
    resumes_folder = "uploads/resumes"
    if os.path.exists(resumes_folder):
        for filename in os.listdir(resumes_folder):
            filepath = os.path.join(resumes_folder, filename)
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

    # 4. Rebuild FAISS index (it will be empty)
    try:
        rebuild_index_from_json()
    except Exception as fe:
        print(f"Error rebuilding FAISS index: {fe}")

    return {
        "success": True,
        "message": "All candidates successfully removed from database, site files, and FAISS index."
    }


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
    import time
    t_start = time.time()

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

    # 1. Load Candidate JSON
    t_load_start = time.time()
    candidate_jsons = {}
    for candidate_name in candidate_names:
        json_path = os.path.join(
            PARSED_JSON_FOLDER,
            f"{candidate_name}.json"
        )
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                candidate_jsons[candidate_name] = json.load(f)
    load_time = time.time() - t_load_start

    # Resolve model name and setup cache
    model_name = os.getenv("OPENAI_MODEL", "gpt-5.5")
    cache_dir = os.path.join(GENERATED_CVS_FOLDER, "cache")
    os.makedirs(cache_dir, exist_ok=True)

    def fetch_cv_json(name, candidate_json):
        # Compute MD5 cache key
        candidate_str = json.dumps(candidate_json, sort_keys=True)
        hasher = hashlib.md5()
        hasher.update(candidate_str.encode("utf-8"))
        hasher.update(jd_text.encode("utf-8"))
        hasher.update(model_name.encode("utf-8"))
        cache_key = hasher.hexdigest()

        cache_path = os.path.join(cache_dir, f"{cache_key}.json")

        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return name, json.load(f), True
            except Exception:
                pass

        # Cache miss: call OpenAI
        cv_json = generate_client_cv_json(candidate_json, jd_text)

        # Write to cache
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cv_json, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

        return name, cv_json, False

    # 2. Generate AI CV (OpenAI)
    t_openai_start = time.time()
    cv_jsons = {}
    with ThreadPoolExecutor(max_workers=max(len(candidate_jsons), 1)) as executor:
        futures = [
            executor.submit(fetch_cv_json, name, candidate_jsons[name])
            for name in candidate_jsons
        ]
        for future in futures:
            name, cv_json, is_cached = future.result()
            cv_jsons[name] = cv_json
    openai_time = time.time() - t_openai_start

    # DOCX helper
    def process_docx(name, cv_json):
        docx_path = os.path.join(
            GENERATED_CVS_FOLDER,
            f"{name}.docx"
        )
        generate_docx(cv_json, docx_path)
        try:
            save_generated_cv_to_db(name, docx_path, jd_text)
        except Exception as e:
            print(f"Error saving generated CV to DB: {e}")
        return docx_path

    # 3. Generate DOCX
    t_docx_start = time.time()
    generated_files = []
    with ThreadPoolExecutor(max_workers=max(len(cv_jsons), 1)) as executor:
        futures = [
            executor.submit(process_docx, name, cv_jsons[name])
            for name in cv_jsons
        ]
        for future in futures:
            try:
                docx_path = future.result()
                generated_files.append(docx_path)
            except Exception as e:
                print(f"Error generating DOCX: {e}")
    docx_time = time.time() - t_docx_start

    if not generated_files:
        raise HTTPException(
            status_code=404,
            detail="No CVs generated"
        )

    # 4. Create ZIP
    t_zip_start = time.time()
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
    zip_time = time.time() - t_zip_start

    # 5. Return Response
    t_resp_start = time.time()
    response = FileResponse(
        zip_path,
        media_type="application/zip",
        filename="selected_cvs.zip"
    )
    response_time = time.time() - t_resp_start

    t_total = time.time() - t_start

    print(f"Load Candidate JSON ............ {load_time:.2f}s")
    print(f"Generate AI CV (OpenAI) ........ {openai_time:.2f}s")
    print(f"Generate DOCX .................. {docx_time:.2f}s")
    print(f"Create ZIP ..................... {zip_time:.2f}s")
    print(f"Return Response ................ {response_time:.2f}s")
    print(f"\nTotal .......................... {t_total:.2f}s\n")

    try:
        breakdown = (
            f"Load Candidate JSON ............ {load_time:.2f}s\n"
            f"Generate AI CV (OpenAI) ........ {openai_time:.2f}s\n"
            f"Generate DOCX .................. {docx_time:.2f}s\n"
            f"Create ZIP ..................... {zip_time:.2f}s\n"
            f"Return Response ................ {response_time:.2f}s\n\n"
            f"Total .......................... {t_total:.2f}s\n"
        )
        with open("profiling_log.txt", "a", encoding="utf-8") as pf:
            pf.write(f"--- Timing Run ---\n{breakdown}\n")
    except Exception:
        pass

    return response


def process_single_resume_worker(filename: str, temp_path: str, content: bytes, model_name: str):
    import time
    import hashlib
    import json
    import os
    from services.extractor import extract_text
    from services.openai_service import parse_resume_with_ai

    try:
        t_extract_start = time.time()
        raw_text = extract_text(temp_path)
        extract_time = time.time() - t_extract_start

        file_hash = hashlib.sha256(content).hexdigest()
        cache_key = hashlib.md5(f"{file_hash}:{model_name}:1.0".encode("utf-8")).hexdigest()
        
        cache_dir = "uploads/resumes/cache"
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{cache_key}.json")

        cached = False
        t_openai_start = time.time()
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as cf:
                    candidate = json.load(cf)
                cached = True
            except Exception:
                pass
        
        if not cached:
            parsed_json = parse_resume_with_ai(raw_text)
            t_json_start = time.time()
            candidate = json.loads(parsed_json)
            json_time = time.time() - t_json_start
            
            try:
                with open(cache_path, "w", encoding="utf-8") as cf:
                    json.dump(candidate, cf, indent=4, ensure_ascii=False)
            except Exception:
                pass
        else:
            json_time = 0.0

        openai_time = time.time() - t_openai_start
        candidate["resume_filename"] = filename
        
        return {
            "success": True,
            "candidate": candidate,
            "raw_text": raw_text,
            "extract_time": extract_time,
            "openai_time": openai_time,
            "json_time": json_time,
            "cached": cached
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/upload-resumes")
async def upload_resumes(
    files: List[UploadFile] = File(...)
):
    import time
    import shutil
    import hashlib
    import json
    import os
    from concurrent.futures import ThreadPoolExecutor
    from services.embedding_service import create_embedding
    from services.faiss_service import rebuild_index_from_json
    from datetime import datetime
    
    t_batch_start = time.time()

    uploaded_candidates = []
    failed_files = []

    os.makedirs("uploads/resumes", exist_ok=True)
    os.makedirs("parsed_json", exist_ok=True)

    # Load statistics configuration from origin/main
    stats_path = "embeddings/upload_stats.json"
    stats = {"new_candidates": 0, "updated_candidates": 0}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r") as f:
                stats = json.load(f)
        except Exception:
            pass

    # 1. Save uploaded files sequentially (async FastAPI handles this)
    valid_files_info = []
    save_timings = {} # maps filename to save time
    
    for file in files:
        if not file.filename:
            failed_files.append({"filename": "unknown", "error": "No filename provided"})
            continue

        filename = os.path.basename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".pdf", ".docx"]:
            failed_files.append({"filename": filename, "error": "Unsupported file type. Only PDF and DOCX are allowed."})
            continue

        t_save_start = time.time()
        import uuid
        temp_path = os.path.join("uploads/resumes", f"temp_{uuid.uuid4().hex}_{filename}")
        try:
            content = await file.read()
            with open(temp_path, "wb") as f:
                f.write(content)
            save_time = time.time() - t_save_start
            save_timings[filename] = save_time
            valid_files_info.append({
                "filename": filename,
                "temp_path": temp_path,
                "content": content,
                "t_start": t_save_start
            })
        except Exception as e:
            failed_files.append({"filename": filename, "error": f"Failed to save temp file: {str(e)}"})
            continue

    # 2. Run Parallel Parsing using ThreadPoolExecutor
    worker_results = {}
    if valid_files_info:
        model_name = os.getenv("OPENAI_MODEL", "gpt-5.5")
        num_workers = min(4, len(valid_files_info))
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(
                    process_single_resume_worker,
                    info["filename"],
                    info["temp_path"],
                    info["content"],
                    model_name
                ): info
                for info in valid_files_info
            }
            
            for future in futures:
                info = futures[future]
                filename = info["filename"]
                try:
                    res = future.result()
                    worker_results[filename] = res
                except Exception as e:
                    worker_results[filename] = {
                        "success": False,
                        "error": str(e)
                    }

    # 3. Process results sequentially (Duplicate check, DB write, Embedding, etc.)
    faiss_time = 0.0
    for info in valid_files_info:
        filename = info["filename"]
        temp_path = info["temp_path"]
        content = info["content"]
        t_start = info["t_start"]
        save_time = save_timings[filename]
        
        res = worker_results.get(filename, {"success": False, "error": "Unknown error occurred during execution"})
        if not res["success"]:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            failed_files.append({"filename": filename, "error": res.get("error", "Parsing failed")})
            continue
            
        candidate = res["candidate"]
        raw_text = res["raw_text"]
        extract_time = res["extract_time"]
        openai_time = res["openai_time"]
        json_time = res["json_time"]
        cached = res["cached"]
        
        try:
            candidate_name = candidate.get("candidate_name", "").strip()
            if not candidate_name:
                raise ValueError("Candidate name could not be parsed from the resume.")

            search_profile = candidate.get("search_profile", "")
            if not search_profile:
                raise ValueError("Search profile could not be generated from the resume.")

            # Overwrite permanent files
            permanent_resume_path = os.path.join("uploads/resumes", filename)
            if os.path.exists(permanent_resume_path):
                os.remove(permanent_resume_path)
            shutil.move(temp_path, permanent_resume_path)
            
            # Database Persistence & Duplicate Check
            t_dup_start = time.time()
            dup_time = 0.0
            db_time = 0.0
            
            try:
                email = extract_email(raw_text)
                phone = extract_phone(raw_text)
                
                db = SessionLocal()
                try:
                    with db_session_lock:
                        db_candidate = None
                        
                        # 1. Search by email (if non-empty)
                        if email:
                            db_candidate = db.query(CandidateModel).filter(
                                CandidateModel.email == email
                            ).first()
                            
                        # 2. Search by phone (if no email match and phone is non-empty)
                        if not db_candidate and phone:
                            db_candidate = db.query(CandidateModel).filter(
                                CandidateModel.phone == phone
                            ).first()
                            
                        # 3. Search by normalized name
                        if not db_candidate and candidate_name:
                            target_norm = normalize_candidate_name(candidate_name)
                            all_candidates = db.query(CandidateModel).all()
                            for cand in all_candidates:
                                if normalize_candidate_name(cand.candidate_name) == target_norm:
                                    db_candidate = cand
                                    break
                        
                        dup_time = time.time() - t_dup_start
                        t_db_start = time.time()
                        
                        if db_candidate:
                            # Duplicate match found! Update existing record and preserve employee_id
                            stats["updated_candidates"] += 1
                            old_safe_name = (
                                db_candidate.candidate_name
                                .replace("/", "_")
                                .replace("\\", "_")
                                .replace(":", "_")
                            )
                            old_json_path = os.path.join("parsed_json", f"{old_safe_name}.json")
                            
                            db_candidate.candidate_name = candidate_name
                            db_candidate.email = email
                            db_candidate.phone = phone
                            db_candidate.original_resume = content
                            db_candidate.original_resume_filename = filename
                            db_candidate.uploaded_at = datetime.utcnow()
                            db.commit()
                            
                            new_safe_name = (
                                candidate_name
                                .replace("/", "_")
                                .replace("\\", "_")
                                .replace(":", "_")
                            )
                            new_json_path = os.path.join("parsed_json", f"{new_safe_name}.json")
                            
                            if old_json_path != new_json_path and os.path.exists(old_json_path):
                                try:
                                    os.remove(old_json_path)
                                except Exception:
                                    pass
                                    
                            with open(new_json_path, "w", encoding="utf-8") as jf:
                                json.dump(candidate, jf, indent=4, ensure_ascii=False)
                        else:
                            # New candidate! Generate new employee_id
                            stats["new_candidates"] += 1
                            emp_id = get_next_employee_id(db)
                            new_candidate = CandidateModel(
                                employee_id=emp_id,
                                candidate_name=candidate_name,
                                email=email,
                                phone=phone,
                                original_resume=content,
                                original_resume_filename=filename,
                                uploaded_at=datetime.utcnow()
                            )
                            db.add(new_candidate)
                            db.commit()
                            
                            new_safe_name = (
                                candidate_name
                                .replace("/", "_")
                                .replace("\\", "_")
                                .replace(":", "_")
                            )
                            new_json_path = os.path.join("parsed_json", f"{new_safe_name}.json")
                            with open(new_json_path, "w", encoding="utf-8") as jf:
                                json.dump(candidate, jf, indent=4, ensure_ascii=False)
                                
                        db_time = time.time() - t_db_start
                finally:
                    db.close()
            except Exception as dbe:
                # If database error occurs, fallback to default parsed_json workflow to guarantee core pipeline runs
                dup_time = time.time() - t_dup_start
                t_db_start = time.time()
                print(f"Database error, using filesystem fallback: {dbe}")
                new_safe_name = (
                    candidate_name
                    .replace("/", "_")
                    .replace("\\", "_")
                    .replace(":", "_")
                )
                new_json_path = os.path.join("parsed_json", f"{new_safe_name}.json")
                with open(new_json_path, "w", encoding="utf-8") as jf:
                    json.dump(candidate, jf, indent=4, ensure_ascii=False)
                db_time = time.time() - t_db_start

            # Embedding Generation
            t_emb_start = time.time()
            embedding = create_embedding(search_profile)
            candidate["embedding"] = embedding
            new_safe_name = (
                candidate_name
                .replace("/", "_")
                .replace("\\", "_")
                .replace(":", "_")
            )
            new_json_path = os.path.join("parsed_json", f"{new_safe_name}.json")
            with open(new_json_path, "w", encoding="utf-8") as jf:
                json.dump(candidate, jf, indent=4, ensure_ascii=False)
                
            emb_time = time.time() - t_emb_start
            
            t_total_single = time.time() - t_start
            
            print(f"\n========================================")
            print(f"TIMING SUMMARY FOR UPLOAD: {filename}")
            print(f"========================================")
            print(f"Save uploaded file ............ {save_time:.2f}s")
            print(f"Extract PDF/DOCX text ......... {extract_time:.2f}s")
            print(f"OpenAI parsing ................ {openai_time:.2f}s ({'cached' if cached else 'live'})")
            print(f"JSON generation ............... {json_time:.2f}s")
            print(f"Duplicate detection ........... {dup_time:.2f}s")
            print(f"Database persistence .......... {db_time:.2f}s")
            print(f"Embedding generation .......... {emb_time:.2f}s")
            print(f"----------------------------------------")
            print(f"Total upload time (single) .... {t_total_single:.2f}s")
            print(f"========================================\n")
            
            uploaded_candidates.append({
                "candidate_name": candidate_name,
                "current_role": candidate.get("current_role", ""),
                "years_of_experience": candidate.get("years_of_experience", 0),
                "filename": filename,
                "single_time": t_total_single,
                "save_time": save_time,
                "extract_time": extract_time,
                "openai_time": openai_time,
                "json_time": json_time,
                "dup_time": dup_time,
                "db_time": db_time,
                "emb_time": emb_time,
                "cached": cached
            })
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            failed_files.append({"filename": filename, "error": str(e)})

    # 4. Batch FAISS indexing
    if uploaded_candidates:
        t_faiss_start = time.time()
        rebuild_index_from_json()
        faiss_time = time.time() - t_faiss_start
        print(f"FAISS indexing time (batch) ... {faiss_time:.2f}s\n")
        
        # Print final timing summary including batch FAISS time
        for cand in uploaded_candidates:
            total_with_faiss = cand["single_time"] + faiss_time
            print(f"========================================")
            print(f"FINAL BATCH TIMING SUMMARY: {cand['filename']}")
            print(f"========================================")
            print(f"Save uploaded file ............ {cand['save_time']:.2f}s")
            print(f"Extract PDF/DOCX text ......... {cand['extract_time']:.2f}s")
            print(f"OpenAI parsing ................ {cand['openai_time']:.2f}s ({'cached' if cand['cached'] else 'live'})")
            print(f"JSON generation ............... {cand['json_time']:.2f}s")
            print(f"Duplicate detection ........... {cand['dup_time']:.2f}s")
            print(f"Database persistence .......... {cand['db_time']:.2f}s")
            print(f"Embedding generation .......... {cand['emb_time']:.2f}s")
            print(f"FAISS indexing ................ {faiss_time:.2f}s")
            print(f"----------------------------------------")
            print(f"Total upload time ............. {total_with_faiss:.2f}s")
            print(f"========================================\n")

    # 5. Save upload statistics
    try:
        os.makedirs(os.path.dirname(stats_path), exist_ok=True)
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=4)
    except Exception:
        pass
            
    return {
        "success": len(failed_files) == 0,
        "uploaded": [
            {
                "candidate_name": c["candidate_name"],
                "current_role": c["current_role"],
                "years_of_experience": c["years_of_experience"],
                "filename": c["filename"]
            }
            for c in uploaded_candidates
        ],
        "failed": failed_files
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


@app.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".docx":
        raise HTTPException(status_code=400, detail="Only DOCX template files are supported.")

    os.makedirs("uploads/templates", exist_ok=True)
    template_path = "uploads/templates/active_template.docx"
    meta_path = "uploads/templates/active_template.json"

    try:
        content = await file.read()
        with open(template_path, "wb") as f:
            f.write(content)

        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump({"original_filename": file.filename}, mf)

        return {
            "success": True,
            "filename": file.filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload template: {str(e)}")


@app.get("/active-template")
def get_active_template():
    template_path = "uploads/templates/active_template.docx"
    meta_path = "uploads/templates/active_template.json"

    if os.path.exists(template_path):
        original_filename = "active_template.docx"
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                    original_filename = meta.get("original_filename", "active_template.docx")
            except Exception:
                pass
        return {
            "exists": True,
            "filename": original_filename
        }
    else:
        return {
            "exists": False,
            "filename": None
        }


@app.delete("/active-template")
def delete_active_template():
    template_path = "uploads/templates/active_template.docx"
    meta_path = "uploads/templates/active_template.json"

    deleted = False
    if os.path.exists(template_path):
        os.remove(template_path)
        deleted = True
    if os.path.exists(meta_path):
        os.remove(meta_path)
        deleted = True

    return {
        "success": deleted,
        "message": "Template removed successfully" if deleted else "No template to remove"
    }


# Reload trigger to force load new database environment variables from .env
