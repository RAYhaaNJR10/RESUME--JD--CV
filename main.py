from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import List
from concurrent.futures import ThreadPoolExecutor

import json
import os
import zipfile
import hashlib
from datetime import datetime

from services.matcher import match_candidates
from services.cv_generator import generate_client_cv_json
from services.docx_generator import generate_docx
from services.comparison_service import compare_candidates
from services.jd_extractor import extract_jd_text
from services.faiss_service import rebuild_index_from_parsed_json
from services.auth_service import hash_password, verify_password, create_access_token, decode_access_token


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

# Protect /dashboard endpoint specifically, before mounting StaticFiles
@app.get("/dashboard")
@app.get("/dashboard/")
def get_dashboard(request: Request):
    try:
        get_current_recruiter(request)
        if not request.url.path.endswith("/"):
            return RedirectResponse(url="/dashboard/")
        return FileResponse(os.path.join(frontend_dir, "index.html"))
    except HTTPException:
        return RedirectResponse(url="/login")

# Serve the static files fallback
app.mount("/dashboard", StaticFiles(directory=frontend_dir, html=True), name="dashboard")

try:
    from db import Base, engine, SessionLocal, CandidateModel, RecruiterModel, DocumentModel, JobDescriptionModel, ApplicationModel, db_session_lock, get_next_employee_id, extract_email, extract_phone, save_generated_cv_to_db, normalize_candidate_name, run_db_migration
    # Run automatic DB schema and file structure migration
    run_db_migration(engine)
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized successfully.")
    
    # Automatically verify and rebuild FAISS indices if empty/missing
    try:
        from services.faiss_service import rebuild_index_from_json, load_index
        db = SessionLocal()
        try:
            recruiters = db.query(RecruiterModel).all()
            
            # Check global index
            global_index = load_index(None)
            if global_index.ntotal == 0:
                print("FAISS global index is empty on startup. Rebuilding from existing profiles...")
                rebuild_index_from_json(recruiter_id=None)
                
            # Check each recruiter's index
            for r in recruiters:
                r_index = load_index(r.recruiter_id)
                if r_index.ntotal == 0:
                    print(f"FAISS index for recruiter {r.recruiter_id} ({r.username}) is empty. Rebuilding...")
                    rebuild_index_from_json(recruiter_id=r.recruiter_id)
        finally:
            db.close()
    except Exception as fe:
        print(f"Failed to check/rebuild FAISS indices on startup: {fe}")
except Exception as e:
    print(f"Database initialization failed: {e}")


PARSED_JSON_FOLDER = "parsed_json"
GENERATED_CVS_FOLDER = "generated_cvs"
JD_UPLOAD_FOLDER = "uploads/jds"


# Helper for current recruiter extraction
def get_current_recruiter(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token or session expired")
        
    username = payload.get("sub")
    db = SessionLocal()
    try:
        recruiter = db.query(RecruiterModel).filter(RecruiterModel.username == username).first()
        if not recruiter:
            raise HTTPException(status_code=401, detail="User not found")
        return recruiter
    finally:
        db.close()


# Ensure default admin recruiter
def ensure_default_admin():
    db = SessionLocal()
    try:
        count = db.query(RecruiterModel).count()
        if count == 0:
            pw_hash = hash_password("admin123")
            admin_user = RecruiterModel(
                username="admin",
                email="admin@example.com",
                password_hash=pw_hash,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(admin_user)
            db.commit()
            print("\n" + "="*80)
            print("WARNING: Default administrator account created!")
            print("Username: admin")
            print("Password: admin123")
            print("IMPORTANT: Please change this default password as soon as possible!")
            print("="*80 + "\n")
    except Exception as e:
        print(f"Failed to check/create default admin recruiter: {e}")
    finally:
        db.close()


ensure_default_admin()


@app.get("/login")
def get_login():
    return FileResponse(os.path.join(frontend_dir, "login.html"))


@app.post("/register")
def register_recruiter(payload: dict):
    username = payload.get("username")
    email = payload.get("email")
    password = payload.get("password")
    
    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="Username, email, and password are required")
        
    db = SessionLocal()
    try:
        existing_username = db.query(RecruiterModel).filter(RecruiterModel.username == username).first()
        if existing_username:
            raise HTTPException(status_code=400, detail="Username already registered")
            
        existing_email = db.query(RecruiterModel).filter(RecruiterModel.email == email).first()
        if existing_email:
            raise HTTPException(status_code=409, detail="An account with this email address already exists.")
            
        pw_hash = hash_password(password)
        new_recruiter = RecruiterModel(
            username=username,
            email=email,
            password_hash=pw_hash,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(new_recruiter)
        db.commit()
        return {"success": True, "message": "Recruiter registered successfully"}
    finally:
        db.close()


@app.post("/login")
def login_recruiter(payload: dict, response: Response):
    username = payload.get("username")
    password = payload.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
        
    db = SessionLocal()
    try:
        recruiter = db.query(RecruiterModel).filter(RecruiterModel.username == username).first()
        if not recruiter or not verify_password(password, recruiter.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
            
        recruiter.last_login = datetime.utcnow()
        db.commit()
        
        # Create token
        token = create_access_token(data={"sub": username})
        
        # Set token in HTTP-only cookie
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            max_age=7200, # 2 hours
            samesite="lax",
            secure=False
        )
        
        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "username": username
        }
    finally:
        db.close()


@app.post("/logout")
def logout_recruiter(response: Response):
    response.delete_cookie(key="access_token")
    return {"success": True, "message": "Logged out successfully"}


@app.get("/current-user")
def get_current_user(recruiter: RecruiterModel = Depends(get_current_recruiter)):
    return {
        "recruiter_id": recruiter.recruiter_id,
        "username": recruiter.username,
        "email": recruiter.email,
        "created_at": recruiter.created_at.isoformat() + "Z" if recruiter.created_at else None,
        "last_login": recruiter.last_login.isoformat() + "Z" if recruiter.last_login else None
    }



@app.get("/")
def home():

    return {
        "message": "Resume JD CV Platform Running"
    }

COMMON_SKILLS = {
    "python", "sql", "aws", "docker", "kubernetes", "git", "ci/cd", "react", "node", "java", "c++",
    "javascript", "typescript", "mysql", "postgresql", "oracle", "mongodb", "linux", "unix", "bash",
    "pyspark", "spark", "hadoop", "etl", "jenkins", "terraform", "ansible", "azure", "gcp", "power bi",
    "tableau", "excel", "html", "css", "django", "flask", "fastapi", "spring", "spring boot", "rest api",
    "microservices", "jira", "scrum", "agile", "incident management", "problem management", "root cause analysis",
    "monitoring", "alerting", "troubleshooting", "production support", "active directory"
}

def process_and_filter_matching_results(
    raw_matches: list,
    jd_text: str,
    db,
    filters: dict
):
    import re
    # Tokenize JD text for matching skills calculations
    jd_text_lower = jd_text.lower()
    
    # Common technologies list for detecting missing skills
    common_skills = COMMON_SKILLS
    
    recruiters = {r.recruiter_id: r.username for r in db.query(RecruiterModel).all()}
    db_candidates = db.query(CandidateModel).all()
    db_cand_map = {c.candidate_name: c for c in db_candidates}
    
    processed_results = []
    
    for match in raw_matches:
        name = match["candidate_name"]
        score = match["score"]
        
        cand = db_cand_map.get(name)
        if not cand:
            continue
            
        uploader_username = recruiters.get(cand.recruiter_id, "unknown")
        
        # Load parsed JSON
        safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        file_path = os.path.join(PARSED_JSON_FOLDER, str(cand.recruiter_id), f"{safe_name}.json")
        
        candidate_skills = []
        candidate_techs = set()
        current_role = ""
        years_of_exp = 0.0
        search_profile = ""
        
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    js = json.load(f)
                candidate_skills = js.get("skills", [])
                current_role = js.get("current_role", "")
                years_of_exp = float(js.get("years_of_experience", 0) or 0)
                search_profile = js.get("search_profile", "")
                
                # Fetch technologies
                for exp in js.get("experience", []):
                    for t in exp.get("technologies", []):
                        candidate_techs.add(t)
                for prj in js.get("projects", []):
                    for t in prj.get("technologies", []):
                        candidate_techs.add(t)
            except Exception:
                pass
                
        # Compute top matching skills
        matching_skills = []
        candidate_all_skills_lower = {s.lower() for s in candidate_skills} | {t.lower() for t in candidate_techs}
        
        for sk in candidate_skills:
            if sk.lower() in jd_text_lower:
                matching_skills.append(sk)
        for t in candidate_techs:
            if t.lower() in jd_text_lower and t not in matching_skills:
                matching_skills.append(t)
                
        # Compute missing skills
        missing_skills = []
        for cs in common_skills:
            if cs in jd_text_lower:
                if cs not in candidate_all_skills_lower:
                    missing_skills.append(cs.title())
                    
        # Apply Filters
        if filters.get("candidate_names"):
            if name not in filters["candidate_names"]:
                continue
                
        if not filters.get("global_pool", True):
            if cand.recruiter_id != filters.get("current_recruiter_id"):
                continue
                
        if filters.get("uploader") and filters["uploader"].lower() != uploader_username.lower():
            continue
            
        if filters.get("role") and filters["role"].lower() not in current_role.lower():
            continue
            
        if filters.get("experience"):
            exp_val = filters["experience"]
            try:
                if "-" in exp_val:
                    parts = exp_val.split("-")
                    exp_min = float(parts[0])
                    exp_max = float(parts[1])
                    if not (exp_min <= years_of_exp <= exp_max):
                        continue
                else:
                    exp_min = float(exp_val)
                    if years_of_exp < exp_min:
                        continue
            except ValueError:
                pass
                
        if filters.get("skills"):
            req_skill = filters["skills"].lower()
            if not any(req_skill in sk.lower() for sk in candidate_skills):
                continue
                
        processed_results.append({
            "candidate_id": cand.candidate_id,
            "candidate_name": name,
            "current_role": current_role,
            "years_of_experience": years_of_exp,
            "uploaded_by": uploader_username,
            "score": score,
            "matching_skills": matching_skills[:8],
            "missing_skills": missing_skills[:8],
            "search_profile": search_profile
        })
        
    return processed_results


@app.post("/rank-candidates")
def rank_candidates(
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    jd_text = payload.get("jd", "")
    if not jd_text:
        raise HTTPException(status_code=400, detail="JD text is required")
        
    global_pool = payload.get("global_pool", True)
    
    # Run FAISS match
    results = match_candidates(
        jd_text,
        top_k=100,
        recruiter_id=None if global_pool else recruiter.recruiter_id
    )
    
    db = SessionLocal()
    try:
        filters = {
            "global_pool": global_pool,
            "current_recruiter_id": recruiter.recruiter_id,
            "experience": payload.get("experience", ""),
            "role": payload.get("role", ""),
            "skills": payload.get("skills", ""),
            "uploader": payload.get("uploader", ""),
            "candidate_names": payload.get("candidate_names", [])
        }
        processed = process_and_filter_matching_results(results, jd_text, db, filters)
        return {
            "count": len(processed),
            "results": processed
        }
    finally:
        db.close()

@app.get("/candidates")
def get_all_candidates(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):

    candidates = []
    rec_parsed_dir = os.path.join(PARSED_JSON_FOLDER, str(recruiter.recruiter_id))

    if not os.path.exists(
        rec_parsed_dir
    ):
        return []

    for filename in os.listdir(
        rec_parsed_dir
    ):

        if not filename.endswith(".json") or filename == "upload_stats.json":
            continue

        file_path = os.path.join(
            rec_parsed_dir,
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
def clear_all_candidates(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    from services.faiss_service import rebuild_index_from_json

    # 1. Clear database candidates table for this recruiter only
    db = SessionLocal()
    try:
        with db_session_lock:
            db.query(CandidateModel).filter(CandidateModel.recruiter_id == recruiter.recruiter_id).delete()
            db.commit()
    except Exception as dbe:
        print(f"Error clearing database candidates: {dbe}")
    finally:
        db.close()

    # 2. Clear parsed JSON folder for this recruiter only
    rec_parsed_dir = os.path.join(PARSED_JSON_FOLDER, str(recruiter.recruiter_id))
    if os.path.exists(rec_parsed_dir):
        for filename in os.listdir(rec_parsed_dir):
            if filename.endswith(".json"):
                try:
                    os.remove(os.path.join(rec_parsed_dir, filename))
                except Exception:
                    pass

    # 3. Clear uploads/resumes files for this recruiter only
    resumes_folder = os.path.join("uploads/resumes", str(recruiter.recruiter_id))
    if os.path.exists(resumes_folder):
        for filename in os.listdir(resumes_folder):
            filepath = os.path.join(resumes_folder, filename)
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

    # 4. Rebuild FAISS index (it will be empty for this recruiter)
    try:
        rebuild_index_from_json(recruiter_id=recruiter.recruiter_id)
        rebuild_index_from_json(recruiter_id=None)
    except Exception as fe:
        print(f"Error rebuilding FAISS index: {fe}")

    return {
        "success": True,
        "message": "All candidates successfully removed from database, site files, and FAISS index."
    }


@app.delete("/candidate/{candidate_name}")
def delete_single_candidate(
    candidate_name: str,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    from services.faiss_service import rebuild_index_from_json
    
    db = SessionLocal()
    try:
        with db_session_lock:
            # Query candidate belonging to this recruiter
            cand = db.query(CandidateModel).filter(
                CandidateModel.candidate_name == candidate_name,
                CandidateModel.recruiter_id == recruiter.recruiter_id
            ).first()
            if not cand:
                raise HTTPException(status_code=404, detail="Candidate not found")
            
            db.delete(cand)
            db.commit()
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
        
    # Delete parsed json on disk for this recruiter
    rec_parsed_dir = os.path.join(PARSED_JSON_FOLDER, str(recruiter.recruiter_id))
    json_path = os.path.join(rec_parsed_dir, f"{candidate_name}.json")
    if os.path.exists(json_path):
        try:
            os.remove(json_path)
        except Exception:
            pass
            
    # Rebuild FAISS index
    try:
        rebuild_index_from_json(recruiter_id=recruiter.recruiter_id)
        rebuild_index_from_json(recruiter_id=None)
    except Exception as fe:
        print(f"Error rebuilding FAISS index: {fe}")
        
    return {"success": True, "message": f"Candidate {candidate_name} successfully deleted."}


@app.post("/candidates/delete-bulk")
def delete_candidates_bulk(
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    """
    Permanently delete one or more candidates owned by the authenticated recruiter.
    Accepts: { "candidate_names": ["Name A", "Name B"] }
    Returns 403 if any candidate belongs to another recruiter.
    Rolls back entire DB transaction on any failure.
    """
    from services.faiss_service import rebuild_index_from_json

    candidate_names = payload.get("candidate_names", [])
    if not candidate_names or not isinstance(candidate_names, list):
        raise HTTPException(status_code=400, detail="candidate_names must be a non-empty list")

    rid = recruiter.recruiter_id
    rec_parsed_dir = os.path.join(PARSED_JSON_FOLDER, str(rid))
    resumes_dir = os.path.join("uploads", "resumes", str(rid))
    generated_cvs_dir = os.path.join(GENERATED_CVS_FOLDER, str(rid))

    db = SessionLocal()
    deleted_names = []
    resume_filenames = []  # track original resume filenames for fs cleanup

    try:
        with db_session_lock:
            # Verify ownership and collect candidates to delete.
            # Three cases per name:
            #  (a) Current recruiter owns it → queue for deletion
            #  (b) Current recruiter does NOT own it AND another recruiter does → 403
            #  (c) Nobody has it → skip (deleted_count stays 0, no error)
            candidates_to_delete = []
            for name in candidate_names:
                own_cand = db.query(CandidateModel).filter(
                    CandidateModel.candidate_name == name,
                    CandidateModel.recruiter_id == rid
                ).first()

                if own_cand:
                    # Case (a): recruiter owns this candidate — queue deletion
                    candidates_to_delete.append(own_cand)
                else:
                    # Case (b): check if a different recruiter owns it
                    foreign_cand = db.query(CandidateModel).filter(
                        CandidateModel.candidate_name == name,
                        CandidateModel.recruiter_id != rid
                    ).first()
                    if foreign_cand:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Forbidden: candidate '{name}' does not belong to your account"
                        )
                    # Case (c): nobody has it — skip silently

            # Delete all queued candidates in one atomic transaction
            for cand in candidates_to_delete:
                if cand.documents and cand.documents.original_resume_filename:
                    resume_filenames.append(cand.documents.original_resume_filename)
                deleted_names.append(cand.candidate_name)
                db.delete(cand)  # cascade deletes Documents + Applications

            db.commit()

    except HTTPException:
        db.rollback()
        db.close()
        raise
    except Exception as e:
        db.rollback()
        db.close()
        raise HTTPException(status_code=500, detail=f"Database error during bulk delete: {str(e)}")
    finally:
        db.close()

    # --- Phase 3: Filesystem cleanup (best-effort, non-fatal) ---
    # Load FAISS embedding cache to remove entries
    from services.faiss_service import get_paths
    import json as _json
    cache_paths = get_paths(rid)
    embedding_cache = {}
    if os.path.exists(cache_paths["cache"]):
        try:
            with open(cache_paths["cache"], "r") as f:
                embedding_cache = _json.load(f)
        except Exception:
            embedding_cache = {}

    cache_modified = False
    for name in deleted_names:
        # 1. Remove parsed JSON file
        json_path = os.path.join(rec_parsed_dir, f"{name}.json")
        if os.path.exists(json_path):
            try:
                os.remove(json_path)
            except Exception as fse:
                print(f"[delete-bulk] Failed to remove parsed JSON for {name}: {fse}")

        # 2. Remove original resume file (by matching candidate name pattern)
        if os.path.exists(resumes_dir):
            # Try exact stored filename first
            removed = False
            for stored_fn in resume_filenames:
                fp = os.path.join(resumes_dir, stored_fn)
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                        removed = True
                    except Exception:
                        pass
            # Fallback: scan for files with candidate name pattern
            if not removed:
                name_slug = name.replace(" ", "_")
                for fn in os.listdir(resumes_dir):
                    if name_slug.lower() in fn.lower():
                        try:
                            os.remove(os.path.join(resumes_dir, fn))
                        except Exception:
                            pass

        # 3. Remove generated CV files
        if os.path.exists(generated_cvs_dir):
            name_slug = name.replace(" ", "_")
            for fn in os.listdir(generated_cvs_dir):
                if name_slug.lower() in fn.lower():
                    try:
                        os.remove(os.path.join(generated_cvs_dir, fn))
                    except Exception:
                        pass

        # 4. Remove from FAISS embedding cache
        for cache_key in [name, f"{name}.json"]:
            if cache_key in embedding_cache:
                del embedding_cache[cache_key]
                cache_modified = True

    # Persist updated embedding cache
    if cache_modified:
        try:
            with open(cache_paths["cache"], "w") as f:
                _json.dump(embedding_cache, f, indent=4)
        except Exception as ce:
            print(f"[delete-bulk] Failed to update embedding cache: {ce}")

    # --- Phase 4: Rebuild FAISS index for this recruiter ---
    try:
        rebuild_index_from_json(recruiter_id=rid)
        rebuild_index_from_json(recruiter_id=None)
    except Exception as fe:
        print(f"[delete-bulk] Error rebuilding FAISS index after bulk delete: {fe}")

    return {
        "success": True,
        "deleted_count": len(deleted_names),
        "deleted": deleted_names,
        "message": f"{len(deleted_names)} candidate(s) permanently deleted."
    }




# First definition of get_candidate_details removed to avoid duplication

@app.post(
    "/upload-jd",
    response_class=PlainTextResponse
)
async def upload_jd(
    file: UploadFile = File(...),
    recruiter: RecruiterModel = Depends(get_current_recruiter)
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
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
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
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
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
        # Locate candidate's JSON profile recursively under PARSED_JSON_FOLDER
        json_path = None
        for root, dirs, files in os.walk(PARSED_JSON_FOLDER):
            if f"{candidate_name}.json" in files:
                json_path = os.path.join(root, f"{candidate_name}.json")
                break
        if json_path and os.path.exists(json_path):
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
        rec_template_dir = os.path.join("uploads/templates", str(recruiter.recruiter_id))
        template_path = os.path.join(rec_template_dir, "active_template.docx")
        generate_docx(cv_json, docx_path, template_path=template_path)
        try:
            save_generated_cv_to_db(name, docx_path, jd_text, recruiter.recruiter_id)
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
            
            # Only cache if the response has a valid candidate_name.
            # This prevents poisoned cache entries from incomplete extractions.
            candidate_name_check = candidate.get("candidate_name", "").strip()
            if candidate_name_check:
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
    files: List[UploadFile] = File(...),
    recruiter: RecruiterModel = Depends(get_current_recruiter)
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

    rec_id_str = str(recruiter.recruiter_id)
    rec_resumes_dir = os.path.join("uploads/resumes", rec_id_str)
    rec_parsed_dir = os.path.join("parsed_json", rec_id_str)
    os.makedirs(rec_resumes_dir, exist_ok=True)
    os.makedirs(rec_parsed_dir, exist_ok=True)

    # Load statistics configuration per recruiter
    stats_path = f"embeddings/{rec_id_str}/upload_stats.json"
    os.makedirs(os.path.dirname(stats_path), exist_ok=True)
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
        temp_path = os.path.join(rec_resumes_dir, f"temp_{uuid.uuid4().hex}_{filename}")
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
                candidate_name = candidate.get("name", "").strip()
            if not candidate_name:
                candidate_name = candidate.get("full_name", "").strip()
                
            if not candidate_name:
                raise ValueError("Candidate name could not be parsed from the resume.")
            
            # Ensure the correct key is populated for the rest of the application
            candidate["candidate_name"] = candidate_name

            search_profile = candidate.get("search_profile", "")
            if not search_profile:
                raise ValueError("Search profile could not be generated from the resume.")

            # Overwrite permanent files
            permanent_resume_path = os.path.join(rec_resumes_dir, filename)
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
                        
                        # 1. Search by email (if non-empty) under this recruiter
                        if email:
                            db_candidate = db.query(CandidateModel).filter(
                                CandidateModel.email == email,
                                CandidateModel.recruiter_id == recruiter.recruiter_id
                            ).first()
                            
                        # 2. Search by phone under this recruiter
                        if not db_candidate and phone:
                            db_candidate = db.query(CandidateModel).filter(
                                CandidateModel.phone == phone,
                                CandidateModel.recruiter_id == recruiter.recruiter_id
                            ).first()
                            
                        # 3. Search by normalized name under this recruiter
                        if not db_candidate and candidate_name:
                            target_norm = normalize_candidate_name(candidate_name)
                            all_candidates = db.query(CandidateModel).filter(
                                CandidateModel.recruiter_id == recruiter.recruiter_id
                            ).all()
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
                            old_json_path = os.path.join(rec_parsed_dir, f"{old_safe_name}.json")
                            
                            db_candidate.candidate_name = candidate_name
                            db_candidate.email = email
                            db_candidate.phone = phone
                            
                            # Update DocumentModel blobs
                            doc = db.query(DocumentModel).filter(DocumentModel.candidate_id == db_candidate.candidate_id).first()
                            if not doc:
                                doc = DocumentModel(candidate_id=db_candidate.candidate_id)
                                db.add(doc)
                            doc.original_resume_blob = content
                            doc.original_resume_filename = filename
                            doc.updated_at = datetime.utcnow()
                            db_candidate.updated_at = datetime.utcnow()
                            
                            db.commit()
                            
                            new_safe_name = (
                                candidate_name
                                .replace("/", "_")
                                .replace("\\", "_")
                                .replace(":", "_")
                            )
                            new_json_path = os.path.join(rec_parsed_dir, f"{new_safe_name}.json")
                            
                            if old_json_path != new_json_path and os.path.exists(old_json_path):
                                try:
                                    os.remove(old_json_path)
                                except Exception:
                                    pass
                                    
                            with open(new_json_path, "w", encoding="utf-8") as jf:
                                json.dump(candidate, jf, indent=4, ensure_ascii=False)
                        else:
                            # New candidate! Generate new employee_id under this recruiter
                            stats["new_candidates"] += 1
                            emp_id = get_next_employee_id(db)
                            new_candidate = CandidateModel(
                                recruiter_id=recruiter.recruiter_id,
                                employee_id=emp_id,
                                candidate_name=candidate_name,
                                email=email,
                                phone=phone,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            db.add(new_candidate)
                            db.commit()
                            db.refresh(new_candidate)
                            
                            # Add DocumentModel blob record
                            new_doc = DocumentModel(
                                candidate_id=new_candidate.candidate_id,
                                original_resume_blob=content,
                                original_resume_filename=filename,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            db.add(new_doc)
                            db.commit()
                            
                            new_safe_name = (
                                candidate_name
                                .replace("/", "_")
                                .replace("\\", "_")
                                .replace(":", "_")
                            )
                            new_json_path = os.path.join(rec_parsed_dir, f"{new_safe_name}.json")
                            with open(new_json_path, "w", encoding="utf-8") as jf:
                                json.dump(candidate, jf, indent=4, ensure_ascii=False)
                                
                        db_time = time.time() - t_db_start
                finally:
                    db.close()
            except Exception as dbe:
                # If database error occurs, fallback to default parsed_json workflow
                dup_time = time.time() - t_dup_start
                t_db_start = time.time()
                print(f"Database error, using filesystem fallback: {dbe}")
                new_safe_name = (
                    candidate_name
                    .replace("/", "_")
                    .replace("\\", "_")
                    .replace(":", "_")
                )
                new_json_path = os.path.join(rec_parsed_dir, f"{new_safe_name}.json")
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
            new_json_path = os.path.join(rec_parsed_dir, f"{new_safe_name}.json")
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
        rebuild_index_from_json(recruiter_id=recruiter.recruiter_id)
        try:
            rebuild_index_from_json(recruiter_id=None)
        except Exception as ge:
            print(f"Error rebuilding global FAISS index: {ge}")
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
def get_upload_stats(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    stats_path = f"embeddings/{recruiter.recruiter_id}/upload_stats.json"
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"new_candidates": 0, "updated_candidates": 0}


@app.post("/reset-upload-stats")
def reset_upload_stats(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    stats_path = f"embeddings/{recruiter.recruiter_id}/upload_stats.json"
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
    rec_parsed_dir = os.path.join(PARSED_JSON_FOLDER, str(recruiter.recruiter_id))
    if os.path.exists(rec_parsed_dir):
        for filename in os.listdir(rec_parsed_dir):
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
    file: UploadFile = File(...),
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".docx":
        raise HTTPException(status_code=400, detail="Only DOCX template files are supported.")

    rec_template_dir = os.path.join("uploads/templates", str(recruiter.recruiter_id))
    os.makedirs(rec_template_dir, exist_ok=True)
    template_path = os.path.join(rec_template_dir, "active_template.docx")
    meta_path = os.path.join(rec_template_dir, "active_template.json")

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
def get_active_template(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    rec_template_dir = os.path.join("uploads/templates", str(recruiter.recruiter_id))
    template_path = os.path.join(rec_template_dir, "active_template.docx")
    meta_path = os.path.join(rec_template_dir, "active_template.json")

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
def delete_active_template(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    rec_template_dir = os.path.join("uploads/templates", str(recruiter.recruiter_id))
    template_path = os.path.join(rec_template_dir, "active_template.docx")
    meta_path = os.path.join(rec_template_dir, "active_template.json")

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
# ==========================================
# MULTI-PAGE PLATFORM REDESIGN ENDPOINTS
# ==========================================

@app.get("/api/candidates")
def api_get_candidates(
    global_pool: bool = False,
    search: str = "",
    recruiter: str = "",
    skills: str = "",
    tech: str = "",
    experience: str = "",
    page: int = 1,
    limit: int = 20,
    sort_by: str = "candidate_name",
    sort_order: str = "asc",
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        query = db.query(CandidateModel)
        if not global_pool:
            query = query.filter(CandidateModel.recruiter_id == current_recruiter.recruiter_id)
        
        db_candidates = query.all()
        candidates_list = []
        
        recruiters = {r.recruiter_id: r.username for r in db.query(RecruiterModel).all()}
        
        for cand in db_candidates:
            safe_name = cand.candidate_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            file_path = os.path.join(PARSED_JSON_FOLDER, str(cand.recruiter_id), f"{safe_name}.json")
            
            cand_data = {
                "candidate_id": cand.candidate_id,
                "candidate_name": cand.candidate_name,
                "employee_id": cand.employee_id,
                "email": cand.email or "",
                "phone": cand.phone or "",
                "location": "",
                "current_role": "",
                "years_of_experience": 0.0,
                "skills": [],
                "technologies": [],
                "uploaded_by": recruiters.get(cand.recruiter_id, "unknown"),
                "created_at": cand.created_at.isoformat(),
                "updated_at": cand.updated_at.isoformat(),
                "filename": ""
            }
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        js = json.load(f)
                    cand_data["current_role"] = js.get("current_role", "")
                    cand_data["years_of_experience"] = float(js.get("years_of_experience", 0) or 0)
                    cand_data["skills"] = js.get("skills", [])
                    cand_data["filename"] = js.get("resume_filename", "")
                    cand_data["location"] = js.get("location", "")
                    
                    techs = set()
                    for exp in js.get("experience", []):
                        for t in exp.get("technologies", []):
                            techs.add(t)
                    for prj in js.get("projects", []):
                        for t in prj.get("technologies", []):
                            techs.add(t)
                    cand_data["technologies"] = list(techs)
                except Exception:
                    pass
            
            if search:
                s_lower = search.lower()
                matches_search = (
                    s_lower in cand_data["candidate_name"].lower() or
                    s_lower in cand_data["current_role"].lower() or
                    s_lower in cand_data["email"].lower() or
                    any(s_lower in sk.lower() for sk in cand_data["skills"])
                )
                if not matches_search:
                    continue
            
            if recruiter and recruiter.lower() != cand_data["uploaded_by"].lower():
                continue
                
            if skills:
                sk_lower = skills.lower()
                if not any(sk_lower in sk.lower() for sk in cand_data["skills"]):
                    continue
                    
            if tech:
                tech_lower = tech.lower()
                if not any(tech_lower in t.lower() for t in cand_data["technologies"]):
                    continue
                    
            if experience:
                try:
                    if "-" in experience:
                        parts = experience.split("-")
                        exp_min = float(parts[0])
                        exp_max = float(parts[1])
                        if not (exp_min <= cand_data["years_of_experience"] <= exp_max):
                            continue
                    else:
                        exp_min = float(experience)
                        if cand_data["years_of_experience"] < exp_min:
                            continue
                except ValueError:
                    pass
                    
            candidates_list.append(cand_data)
            
        reverse = (sort_order.lower() == "desc")
        if sort_by in ["created_at", "upload_date"]:
            candidates_list.sort(key=lambda x: x["created_at"], reverse=reverse)
        elif sort_by in ["years_of_experience", "experience"]:
            candidates_list.sort(key=lambda x: x["years_of_experience"], reverse=reverse)
        elif sort_by == "current_role":
            candidates_list.sort(key=lambda x: x["current_role"].lower(), reverse=reverse)
        else:
            candidates_list.sort(key=lambda x: x["candidate_name"].lower(), reverse=reverse)
            
        total = len(candidates_list)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_results = candidates_list[start_idx:end_idx]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "results": paginated_results
        }
    finally:
        db.close()


@app.get("/api/candidates/metadata")
def api_get_candidates_metadata(
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        recruiters = [r.username for r in db.query(RecruiterModel).all()]
        all_candidates = db.query(CandidateModel).all()
        unique_skills = set()
        unique_techs = set()
        unique_roles = set()
        
        for cand in all_candidates:
            safe_name = cand.candidate_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            file_path = os.path.join(PARSED_JSON_FOLDER, str(cand.recruiter_id), f"{safe_name}.json")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        js = json.load(f)
                    
                    role = js.get("current_role", "")
                    if role:
                        unique_roles.add(role.strip())
                        
                    for sk in js.get("skills", []):
                        if sk:
                            unique_skills.add(sk.strip())
                            
                    for exp in js.get("experience", []):
                        for t in exp.get("technologies", []):
                            unique_techs.add(t.strip())
                    for prj in js.get("projects", []):
                        for t in prj.get("technologies", []):
                            unique_techs.add(t.strip())
                except Exception:
                    pass
                    
        return {
            "recruiters": sorted(list(recruiters)),
            "skills": sorted(list(unique_skills))[:100],
            "technologies": sorted(list(unique_techs))[:100],
            "roles": sorted(list(unique_roles))[:100]
        }
    finally:
        db.close()


# Overwrite get_candidate_details to query across recruiters
@app.get("/candidate/{candidate_name}")
def get_candidate_details(
    candidate_name: str,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        # Search candidate globally in DB
        cand = db.query(CandidateModel).filter(CandidateModel.candidate_name == candidate_name).first()
        cand_recruiter_id = cand.recruiter_id if cand else recruiter.recruiter_id
        
        # 1. Load parsed JSON (primary source)
        safe_name = (
            candidate_name
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
        )
        file_path = os.path.join(
            PARSED_JSON_FOLDER,
            str(cand_recruiter_id),
            f"{safe_name}.json"
        )
        
        # Fallback recursive walk search if exact folder path is missing
        if not os.path.exists(file_path):
            file_path = None
            for root, dirs, files in os.walk(PARSED_JSON_FOLDER):
                if f"{safe_name}.json" in files:
                    file_path = os.path.join(root, f"{safe_name}.json")
                    break
        
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail="Candidate not found"
            )
            
        with open(file_path, "r", encoding="utf-8") as f:
            candidate_data = json.load(f)
            
        # Remove raw embedding vector — never needed by the frontend
        candidate_data.pop("embedding", None)
        
        # 2. Promote search_profile → about_candidate / professional_summary if missing
        if not candidate_data.get("about_candidate"):
            candidate_data["about_candidate"] = candidate_data.get("search_profile", "")
        if not candidate_data.get("professional_summary"):
            candidate_data["professional_summary"] = candidate_data.get("about_candidate", "")
            
        # 3. Ensure experience entries have consistent field names
        for exp in candidate_data.get("experience", []):
            # Normalize role aliases
            if not exp.get("role") and exp.get("title"):
                exp["role"] = exp["title"]
            # Normalize date aliases
            if not exp.get("duration"):
                start = exp.get("start_date", "") or exp.get("start_year", "")
                end   = exp.get("end_date",   "") or exp.get("end_year",   "")
                if start or end:
                    exp["duration"] = f"{start} – {end}".strip(" –")

        # 4. Merge DB fields
        if cand:
            # Email & Phone from DB (fallback if missing or empty in JSON)
            if cand.email and not candidate_data.get("email"):
                candidate_data["email"] = cand.email
            if cand.phone and not candidate_data.get("phone"):
                candidate_data["phone"] = cand.phone
                
            candidate_data["employee_id"] = cand.employee_id or ""
            candidate_data["created_at"]  = str(cand.created_at) if cand.created_at else ""
            candidate_data["uploaded_date"] = cand.created_at.isoformat() if cand.created_at else ""
            candidate_data["candidate_id"] = cand.candidate_id
            
            # Uploader username
            uploader = db.query(RecruiterModel).filter(
                RecruiterModel.recruiter_id == cand.recruiter_id
            ).first()
            candidate_data["uploaded_by"] = uploader.username if uploader else ""
            
            # Resume filename from DocumentModel
            doc = db.query(DocumentModel).filter(
                DocumentModel.candidate_id == cand.candidate_id
            ).first()
            if doc and doc.original_resume_filename:
                candidate_data["resume_filename"] = doc.original_resume_filename
                
            # Resume download URL
            candidate_data["resume_url"] = (
                f"/api/candidates/{cand.candidate_id}/download-resume"
                if doc else ""
            )
        else:
            candidate_data.setdefault("employee_id", "")
            candidate_data.setdefault("uploaded_by", "")
            candidate_data.setdefault("created_at",  "")
            candidate_data.setdefault("uploaded_date", "")
            candidate_data.setdefault("resume_url",  "")
            
        # 5. Ensure all expected fields exist with empty defaults
        candidate_data.setdefault("candidate_name",      candidate_name)
        candidate_data.setdefault("current_role",        "")
        candidate_data.setdefault("years_of_experience", 0)
        candidate_data.setdefault("email",               "")
        candidate_data.setdefault("phone",               "")
        candidate_data.setdefault("location",            "")
        candidate_data.setdefault("linkedin",            "")
        candidate_data.setdefault("github",              "")
        candidate_data.setdefault("about_candidate",     "")
        candidate_data.setdefault("skills",              [])
        candidate_data.setdefault("domains",             [])
        candidate_data.setdefault("experience",          [])
        candidate_data.setdefault("education",           [])
        candidate_data.setdefault("projects",            [])
        candidate_data.setdefault("resume_filename",     "")
        
        return candidate_data
    finally:
        db.close()



# Job Description CRUD APIs
@app.post("/api/job-descriptions")
def create_job_description(
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    title = payload.get("title")
    description = payload.get("description")
    if not title or not description:
        raise HTTPException(status_code=400, detail="Title and description are required")
    db = SessionLocal()
    try:
        jd = JobDescriptionModel(
            recruiter_id=recruiter.recruiter_id,
            short_title=title,
            full_description=description,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(jd)
        db.commit()
        db.refresh(jd)
        return {"success": True, "jd_id": jd.jd_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/job-descriptions")
def list_job_descriptions(
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        jds = db.query(JobDescriptionModel).all()
        results = []
        for jd in jds:
            uploader = db.query(RecruiterModel).filter(RecruiterModel.recruiter_id == jd.recruiter_id).first()
            match_count = db.query(ApplicationModel).filter(ApplicationModel.jd_id == jd.jd_id).count()
            results.append({
                "jd_id": jd.jd_id,
                "title": jd.short_title,
                "description": jd.full_description,
                "created_by": uploader.username if uploader else "unknown",
                "created_date": jd.created_at.isoformat(),
                "match_count": match_count
            })
        return results
    finally:
        db.close()


@app.get("/api/job-descriptions/{jd_id}")
def get_job_description(
    jd_id: int,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        jd = db.query(JobDescriptionModel).filter(JobDescriptionModel.jd_id == jd_id).first()
        if not jd:
            raise HTTPException(status_code=404, detail="Job description not found")
        uploader = db.query(RecruiterModel).filter(RecruiterModel.recruiter_id == jd.recruiter_id).first()
        return {
            "jd_id": jd.jd_id,
            "title": jd.short_title,
            "description": jd.full_description,
            "created_by": uploader.username if uploader else "unknown",
            "created_date": jd.created_at.isoformat()
        }
    finally:
        db.close()


@app.put("/api/job-descriptions/{jd_id}")
def update_job_description(
    jd_id: int,
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    title = payload.get("title")
    description = payload.get("description")
    if not title or not description:
        raise HTTPException(status_code=400, detail="Title and description are required")
    db = SessionLocal()
    try:
        jd = db.query(JobDescriptionModel).filter(JobDescriptionModel.jd_id == jd_id).first()
        if not jd:
            raise HTTPException(status_code=404, detail="Job description not found")
        jd.short_title = title
        jd.full_description = description
        jd.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.delete("/api/job-descriptions/{jd_id}")
def delete_job_description(
    jd_id: int,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        jd = db.query(JobDescriptionModel).filter(JobDescriptionModel.jd_id == jd_id).first()
        if not jd:
            raise HTTPException(status_code=404, detail="Job description not found")
        db.delete(jd)
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/job-descriptions/{jd_id}/matches")
def api_get_jd_matches(
    jd_id: int,
    global_pool: bool = True,
    experience: str = "",
    role: str = "",
    skills: str = "",
    uploader: str = "",
    candidate_names: str = "",
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        jd = db.query(JobDescriptionModel).filter(JobDescriptionModel.jd_id == jd_id).first()
        if not jd:
            raise HTTPException(status_code=404, detail="Job description not found")
        
        results = match_candidates(
            jd.full_description,
            top_k=100,
            recruiter_id=None if global_pool else current_recruiter.recruiter_id
        )
        
        cand_list = []
        if candidate_names:
            cand_list = [n.strip() for n in candidate_names.split(",") if n.strip()]
            
        filters = {
            "global_pool": global_pool,
            "current_recruiter_id": current_recruiter.recruiter_id,
            "experience": experience,
            "role": role,
            "skills": skills,
            "uploader": uploader,
            "candidate_names": cand_list
        }
        
        processed = process_and_filter_matching_results(results, jd.full_description, db, filters)
        return processed
    finally:
        db.close()


# ────────────────────────────────────────────────────────────
# AI SEMANTIC TALENT SEARCH
# Reuses existing embedding_service + faiss_service
# ────────────────────────────────────────────────────────────
@app.post("/api/candidates/semantic-search")
def api_semantic_talent_search(
    payload: dict,
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    from services.embedding_service import create_embedding
    from services.faiss_service import search_candidates

    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query is required.")

    min_score        = float(payload.get("min_score", 0.10))
    exp_filter       = payload.get("experience", "")
    role_filter      = payload.get("role", "")
    recruiter_filter = payload.get("recruiter", "")
    page             = max(1, int(payload.get("page", 1)))
    limit            = max(1, int(payload.get("limit", 20)))

    try:
        query_embedding = create_embedding(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding service error: {e}")

    raw_matches = search_candidates(query_embedding, top_k=200, recruiter_id=None)

    db = SessionLocal()
    try:
        recruiters  = {r.recruiter_id: r.username for r in db.query(RecruiterModel).all()}
        db_cand_map = {c.candidate_name: c for c in db.query(CandidateModel).all()}

        TECH_INDICATORS = {
            "docker","kubernetes","mysql","postgresql","mongodb","redis",
            "elasticsearch","kafka","rabbitmq","react","vue","angular",
            "jenkins","terraform","ansible","git","gitlab","github",
            "autosys","splunk","dynatrace","appdynamics","prometheus","grafana",
            "airflow","spark","hadoop","snowflake","databricks","dbt"
        }

        enriched = []
        for match in raw_matches:
            score = float(match["score"])
            if score < min_score:
                continue

            name = match["candidate_name"]
            cand = db_cand_map.get(name)
            if not cand:
                continue

            uploader = recruiters.get(cand.recruiter_id, "unknown")
            if recruiter_filter and recruiter_filter.lower() != uploader.lower():
                continue

            safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
            file_path = os.path.join(PARSED_JSON_FOLDER, str(cand.recruiter_id), f"{safe_name}.json")

            profile_data = {}
            skills = []
            current_role = ""
            years_of_exp = 0.0
            about = ""

            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        profile_data = json.load(f)
                    skills       = profile_data.get("skills", [])
                    current_role = profile_data.get("current_role", "")
                    years_of_exp = float(profile_data.get("years_of_experience", 0) or 0)
                    about        = profile_data.get("about_candidate", "")
                except Exception:
                    pass

            if role_filter and role_filter.lower() not in current_role.lower():
                continue
            if exp_filter:
                try:
                    if "-" in exp_filter:
                        lo, hi = (float(x) for x in exp_filter.split("-"))
                        if not (lo <= years_of_exp <= hi):
                            continue
                    else:
                        if years_of_exp < float(exp_filter):
                            continue
                except ValueError:
                    pass

            techs = set()
            for exp_item in profile_data.get("experience", []):
                techs.update(exp_item.get("technologies", []))
            for prj in profile_data.get("projects", []):
                techs.update(prj.get("technologies", []))

            from services.comparison_service import infer_strengths
            strengths = infer_strengths(profile_data)

            query_lower = query.lower()
            cand_all_lower = {s.lower() for s in skills} | {t.lower() for t in techs}

            matching_skills  = [sk for sk in skills if sk.lower() in query_lower]
            matching_tech    = [t  for t  in sorted(techs) if t.lower() in query_lower]
            matching_domains = [d  for d  in profile_data.get("domains", []) if d.lower() in query_lower]

            matching_exp = ""
            if current_role and any(tok in current_role.lower() for tok in query_lower.split() if len(tok) > 3):
                matching_exp = f"{years_of_exp} years as {current_role}"
            else:
                for exp_item in profile_data.get("experience", []):
                    r = exp_item.get("role", "") or exp_item.get("title", "")
                    if r and any(tok in r.lower() for tok in query_lower.split() if len(tok) > 3):
                        dur = exp_item.get("duration", "")
                        matching_exp = f"Experience as {r}" + (f" ({dur})" if dur else "")
                        break
            if not matching_exp:
                matching_exp = f"{years_of_exp} years of overall experience"

            missing_skills = []
            missing_tech   = []
            for cs in COMMON_SKILLS:
                if cs in query_lower and cs not in cand_all_lower:
                    label = cs.title()
                    if cs in TECH_INDICATORS:
                        missing_tech.append(label)
                    else:
                        missing_skills.append(label)

            import re as _re
            missing_exp = ""
            _m = _re.search(r"(\d+)\+?\s*years?", query_lower)
            if _m:
                req_yrs = float(_m.group(1))
                if years_of_exp < req_yrs:
                    missing_exp = f"Requires {req_yrs}+ years (candidate has {years_of_exp})"

            enriched.append({
                "candidate_id":        cand.candidate_id,
                "candidate_name":      name,
                "current_role":        current_role,
                "years_of_experience": years_of_exp,
                "uploaded_by":         uploader,
                "score":               score,
                "skills":              skills[:10],
                "technologies":        sorted(list(techs))[:8],
                "matching_skills":     matching_skills[:8],
                "missing_skills":      missing_skills[:6],
                "about_candidate":     about,
                "strengths":           strengths,
                "match_details": {
                    "matching_skills":  matching_skills,
                    "matching_tech":    matching_tech,
                    "matching_domains": matching_domains,
                    "matching_exp":     matching_exp,
                    "missing_skills":   missing_skills,
                    "missing_tech":     missing_tech,
                    "missing_exp":      missing_exp,
                },
                "_profile": profile_data,
            })

    finally:
        db.close()

    total = len(enriched)
    if total == 0:
        return {
            "total": 0, "page": page, "limit": limit, "query": query,
            "results": [],
            "message": "No relevant candidates were found. Try broadening your search or upload additional resumes."
        }

    page_slice = enriched[(page - 1) * limit: page * limit]

    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv()
    _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _generate_explanation(item):
        try:
            sks   = ", ".join(item["skills"][:6]) if item["skills"] else "N/A"
            about = (item["about_candidate"] or "")[:300]
            prompt = (
                f"You are a recruitment assistant. In ONE concise sentence (max 25 words), "
                f"explain why this candidate matches the search query: \"{query}\".\n\n"
                f"Candidate: {item['candidate_name']}\n"
                f"Role: {item['current_role']}\n"
                f"Experience: {item['years_of_experience']} years\n"
                f"Key skills: {sks}\n"
                f"Profile: {about}\n\n"
                f"Respond with only the single explanation sentence."
            )
            resp = _openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.4
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return ""

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_generate_explanation, item): i for i, item in enumerate(page_slice)}
        explanations = [""] * len(page_slice)
        for future, i in futures.items():
            try:
                explanations[i] = future.result(timeout=15)
            except Exception:
                pass

    results_out = []
    for i, item in enumerate(page_slice):
        item.pop("_profile", None)
        item["explanation"] = explanations[i]
        item["score_pct"]   = round(item["score"] * 100, 1)
        results_out.append(item)

    return {
        "total":   total,
        "page":    page,
        "limit":   limit,
        "query":   query,
        "results": results_out
    }



@app.get("/api/generated-cvs")
def api_get_generated_cvs(
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        docs = db.query(DocumentModel).filter(DocumentModel.generated_cv_blob != None).all()
        results = []
        recruiters = {r.recruiter_id: r.username for r in db.query(RecruiterModel).all()}
        
        for doc in docs:
            cand = db.query(CandidateModel).filter(CandidateModel.candidate_id == doc.candidate_id).first()
            if not cand:
                continue
                
            app = db.query(ApplicationModel).filter(
                ApplicationModel.candidate_id == cand.candidate_id,
                ApplicationModel.status == "CV_GENERATED"
            ).first()
            
            jd_title = "General"
            if app:
                jd = db.query(JobDescriptionModel).filter(JobDescriptionModel.jd_id == app.jd_id).first()
                if jd:
                    jd_title = jd.short_title
            
            results.append({
                "candidate_id": cand.candidate_id,
                "candidate_name": cand.candidate_name,
                "generated_cv_filename": doc.generated_cv_filename,
                "jd_title": jd_title,
                "generated_by": recruiters.get(cand.recruiter_id, "unknown"),
                "generated_date": doc.updated_at.isoformat()
            })
            
        return results
    finally:
        db.close()


@app.get("/api/generated-cvs/{candidate_id}/download")
def api_download_generated_cv(
    candidate_id: int,
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        doc = db.query(DocumentModel).filter(DocumentModel.candidate_id == candidate_id).first()
        if not doc or not doc.generated_cv_blob:
            raise HTTPException(status_code=404, detail="Generated CV not found")
        
        import io
        from fastapi.responses import StreamingResponse
        
        headers = {
            "Content-Disposition": f"attachment; filename=\"{doc.generated_cv_filename}\""
        }
        return StreamingResponse(
            io.BytesIO(doc.generated_cv_blob),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers
        )
    finally:
        db.close()


@app.get("/api/candidates/{candidate_id}/download-resume")
def api_download_original_resume(
    candidate_id: int,
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        doc = db.query(DocumentModel).filter(DocumentModel.candidate_id == candidate_id).first()
        if not doc or not doc.original_resume_blob:
            raise HTTPException(status_code=404, detail="Original resume not found")
        
        import io
        from fastapi.responses import StreamingResponse
        
        filename = doc.original_resume_filename or "resume.pdf"
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".docx":
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            media_type = "application/pdf"
            
        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
        return StreamingResponse(
            io.BytesIO(doc.original_resume_blob),
            media_type=media_type,
            headers=headers
        )
    finally:
        db.close()



@app.delete("/api/generated-cvs/{candidate_id}")
def api_delete_generated_cv(
    candidate_id: int,
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        doc = db.query(DocumentModel).filter(DocumentModel.candidate_id == candidate_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Clear generated CV filename and blob
        doc.generated_cv_blob = None
        doc.generated_cv_filename = None
        doc.updated_at = datetime.utcnow()
        
        # Also find any associated Application and revert its status if it was CV_GENERATED
        app = db.query(ApplicationModel).filter(
            ApplicationModel.candidate_id == candidate_id,
            ApplicationModel.status == "CV_GENERATED"
        ).first()
        if app:
            app.status = "MATCHED"
            
        db.commit()
        return {"success": True, "message": "Generated CV deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# Company Analytics API
@app.get("/api/analytics")
def api_get_analytics(
    current_recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    db = SessionLocal()
    try:
        recruiters = db.query(RecruiterModel).all()
        recruiter_mapping = {r.recruiter_id: r.username for r in recruiters}
        recruiter_counts = {}
        for r in recruiters:
            recruiter_counts[r.username] = 0
            
        all_candidates = db.query(CandidateModel).all()
        for cand in all_candidates:
            username = recruiter_mapping.get(cand.recruiter_id, "unknown")
            recruiter_counts[username] = recruiter_counts.get(username, 0) + 1
            
        unique_skills = {}
        exp_dist = {"Fresher (0 yrs)": 0, "1-3 Years": 0, "3-5 Years": 0, "5-10 Years": 0, "10+ Years": 0}
        
        for cand in all_candidates:
            safe_name = cand.candidate_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            file_path = os.path.join(PARSED_JSON_FOLDER, str(cand.recruiter_id), f"{safe_name}.json")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        js = json.load(f)
                    
                    yrs = float(js.get("years_of_experience", 0) or 0)
                    if yrs == 0:
                        exp_dist["Fresher (0 yrs)"] += 1
                    elif yrs <= 3:
                        exp_dist["1-3 Years"] += 1
                    elif yrs <= 5:
                        exp_dist["3-5 Years"] += 1
                    elif yrs <= 10:
                        exp_dist["5-10 Years"] += 1
                    else:
                        exp_dist["10+ Years"] += 1
                        
                    for sk in js.get("skills", []):
                        sk_clean = sk.strip().title()
                        if sk_clean:
                            unique_skills[sk_clean] = unique_skills.get(sk_clean, 0) + 1
                except Exception:
                    pass
                    
        top_skills = sorted(unique_skills.items(), key=lambda x: x[1], reverse=True)[:10]
        top_skills_dict = {k: v for k, v in top_skills}
        
        jds = db.query(JobDescriptionModel).all()
        jd_counts = []
        for jd in jds:
            usage = db.query(ApplicationModel).filter(ApplicationModel.jd_id == jd.jd_id).count()
            jd_counts.append({"title": jd.short_title, "count": usage})
        jd_counts = sorted(jd_counts, key=lambda x: x["count"], reverse=True)[:5]
        
        scores = db.query(ApplicationModel.similarity_score).filter(ApplicationModel.similarity_score != None).all()
        avg_score = 0.0
        if scores:
            avg_score = sum(s[0] for s in scores) / len(scores)
            
        from sqlalchemy import func
        trend_query = db.query(
            func.date(CandidateModel.created_at),
            func.count(CandidateModel.candidate_id)
        ).group_by(func.date(CandidateModel.created_at)).order_by(func.date(CandidateModel.created_at)).all()
        
        upload_trends = {str(d): count for d, count in trend_query}
        
        return {
            "recruiter_distribution": recruiter_counts,
            "experience_distribution": exp_dist,
            "skill_distribution": top_skills_dict,
            "most_used_jds": jd_counts,
            "average_match_score": round(avg_score * 100, 1) if avg_score else 0.0,
            "upload_trends": upload_trends
        }
    finally:
        db.close()


@app.post("/api/change-password")
def change_password(
    payload: dict,
    recruiter: RecruiterModel = Depends(get_current_recruiter)
):
    old_password = payload.get("old_password")
    new_password = payload.get("new_password")
    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="Current and new password are required")
        
    db = SessionLocal()
    try:
        rec = db.query(RecruiterModel).filter(RecruiterModel.recruiter_id == recruiter.recruiter_id).first()
        if not rec or not verify_password(old_password, rec.password_hash):
            raise HTTPException(status_code=400, detail="Invalid current password")
            
        rec.password_hash = hash_password(new_password)
        rec.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True, "message": "Password changed successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

