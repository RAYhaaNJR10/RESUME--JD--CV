import os
import re
import json
import threading
import shutil
from datetime import datetime
from dotenv import load_dotenv

# Ensure env variables are loaded from the backend folder relative to this file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, LargeBinary, ForeignKey, Float, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import pymysql

# Load database environment variables
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "resume_platform")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")

# Global lock for thread-safe database operations (e.g. employee ID generation)
db_session_lock = threading.Lock()

def ensure_database_exists():
    """Ensure the target database exists in MySQL before creating SQLAlchemy engine."""
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=int(DB_PORT),
            user=DB_USER,
            password=DB_PASSWORD
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        conn.close()
        print(f"Database '{DB_NAME}' verified/created successfully.")
    except Exception as e:
        print(f"Error ensuring database exists: {e}")

# Run database verification
ensure_database_exists()

# Setup SQLAlchemy Connection
DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class RecruiterModel(Base):
    __tablename__ = "recruiters"

    recruiter_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(150), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    candidates = relationship("CandidateModel", back_populates="recruiter", cascade="all, delete-orphan")
    job_descriptions = relationship("JobDescriptionModel", back_populates="recruiter", cascade="all, delete-orphan")


class CandidateModel(Base):
    __tablename__ = "candidates"

    candidate_id = Column(Integer, primary_key=True, autoincrement=True)
    recruiter_id = Column(Integer, ForeignKey("recruiters.recruiter_id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(String(20), unique=True, nullable=False)
    candidate_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    recruiter = relationship("RecruiterModel", back_populates="candidates")
    documents = relationship("DocumentModel", back_populates="candidate", cascade="all, delete-orphan", uselist=False)
    applications = relationship("ApplicationModel", back_populates="candidate", cascade="all, delete-orphan")


class JobDescriptionModel(Base):
    __tablename__ = "job_descriptions"

    jd_id = Column(Integer, primary_key=True, autoincrement=True)
    recruiter_id = Column(Integer, ForeignKey("recruiters.recruiter_id", ondelete="CASCADE"), nullable=False)
    short_title = Column(String(255), nullable=False)
    full_description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    recruiter = relationship("RecruiterModel", back_populates="job_descriptions")
    applications = relationship("ApplicationModel", back_populates="job_description", cascade="all, delete-orphan")


class DocumentModel(Base):
    __tablename__ = "documents"

    document_id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, unique=True)
    original_resume_blob = Column(LargeBinary().with_variant(LONGBLOB, "mysql"), nullable=True)
    original_resume_filename = Column(String(255), nullable=True)
    generated_cv_blob = Column(LargeBinary().with_variant(LONGBLOB, "mysql"), nullable=True)
    generated_cv_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    candidate = relationship("CandidateModel", back_populates="documents")


class ApplicationModel(Base):
    __tablename__ = "applications"

    application_id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False)
    jd_id = Column(Integer, ForeignKey("job_descriptions.jd_id", ondelete="CASCADE"), nullable=False)
    similarity_score = Column(Float, nullable=True)
    status = Column(String(50), nullable=False, default="PARSED")  # PARSED, MATCHED, CV_GENERATED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    candidate = relationship("CandidateModel", back_populates="applications")
    job_description = relationship("JobDescriptionModel", back_populates="applications")


def normalize_candidate_name(name: str) -> str:
    """Normalize candidate name by converting to lowercase, removing punctuation, trimming whitespace, and collapsing multiple spaces."""
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r'[^\w\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def extract_email(text: str) -> str:
    """Extract first email address from text using regex."""
    if not text:
        return ""
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0).strip() if match else ""


def extract_phone(text: str) -> str:
    """Extract phone number from text using regex."""
    if not text:
        return ""
    match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+?\d{10,12}', text)
    return match.group(0).strip() if match else ""


def extract_job_role(jd_text: str) -> str:
    """Extract a short, recruiter-friendly label for the job role from the JD."""
    if not jd_text:
        return "Unknown Role"
    lines = [line.strip() for line in jd_text.split('\n') if line.strip()]
    
    for line in lines[:3]:
        match = re.search(r'(?:role|title|position|job)\s*:\s*(.+)', line, re.IGNORECASE)
        if match:
            return match.group(1)[:50].strip()
            
    if lines:
        return lines[0][:50].strip()
    return "Unknown Role"


def extract_job_description_summary(jd_text: str) -> str:
    """Extract a brief summary of the JD text (first 3-4 lines, max 500 chars)."""
    if not jd_text:
        return ""
    lines = [line.strip() for line in jd_text.split('\n') if line.strip()]
    summary = " ".join(lines[:4])
    if len(summary) > 500:
        summary = summary[:497] + "..."
    return summary


def get_next_employee_id(db_session) -> str:
    """Generates the next employee ID in the format EMP0001, EMP0002, etc. (Not thread-safe on its own, call inside lock)."""
    latest = db_session.query(CandidateModel).order_by(CandidateModel.candidate_id.desc()).first()
    if latest and latest.employee_id.startswith("EMP"):
        try:
            num = int(latest.employee_id[3:])
            return f"EMP{num + 1:04d}"
        except ValueError:
            pass
    
    count = db_session.query(CandidateModel).count()
    return f"EMP{count + 1:04d}"


def save_generated_cv_to_db(candidate_name: str, docx_path: str, jd_text: str, recruiter_id: int):
    """Saves generated DOCX bytes and JD summary to the database, updating the candidate record."""
    if not os.path.exists(docx_path):
        return

    with open(docx_path, "rb") as f:
        docx_bytes = f.read()

    filename = os.path.basename(docx_path)
    job_role = extract_job_role(jd_text)

    db = SessionLocal()
    try:
        with db_session_lock:
            db_candidate = db.query(CandidateModel).filter(
                CandidateModel.candidate_name == candidate_name,
                CandidateModel.recruiter_id == recruiter_id
            ).first()
            
            if db_candidate:
                doc = db.query(DocumentModel).filter(DocumentModel.candidate_id == db_candidate.candidate_id).first()
                if not doc:
                    doc = DocumentModel(candidate_id=db_candidate.candidate_id)
                    db.add(doc)
                doc.generated_cv_blob = docx_bytes
                doc.generated_cv_filename = filename
                doc.updated_at = datetime.utcnow()
                db_candidate.updated_at = datetime.utcnow()
                
                # Retrieve or create JobDescription
                jd = db.query(JobDescriptionModel).filter(
                    JobDescriptionModel.recruiter_id == recruiter_id,
                    JobDescriptionModel.full_description == jd_text
                ).first()
                if not jd:
                    jd = JobDescriptionModel(
                        recruiter_id=recruiter_id,
                        short_title=job_role,
                        full_description=jd_text
                    )
                    db.add(jd)
                    db.commit()
                    db.refresh(jd)
                
                # Retrieve or create Application
                app = db.query(ApplicationModel).filter(
                    ApplicationModel.candidate_id == db_candidate.candidate_id,
                    ApplicationModel.jd_id == jd.jd_id
                ).first()
                if not app:
                    app = ApplicationModel(
                        candidate_id=db_candidate.candidate_id,
                        jd_id=jd.jd_id,
                        status="CV_GENERATED"
                    )
                    db.add(app)
                else:
                    app.status = "CV_GENERATED"
                    app.updated_at = datetime.utcnow()
                db.commit()
                print(f"Updated CV for candidate '{candidate_name}' (ID: {db_candidate.employee_id}) in DB.")
            else:
                emp_id = get_next_employee_id(db)
                new_cand = CandidateModel(
                    recruiter_id=recruiter_id,
                    employee_id=emp_id,
                    candidate_name=candidate_name,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_cand)
                db.commit()
                db.refresh(new_cand)
                
                doc = DocumentModel(
                    candidate_id=new_cand.candidate_id,
                    generated_cv_blob=docx_bytes,
                    generated_cv_filename=filename
                )
                db.add(doc)
                
                jd = db.query(JobDescriptionModel).filter(
                    JobDescriptionModel.recruiter_id == recruiter_id,
                    JobDescriptionModel.full_description == jd_text
                ).first()
                if not jd:
                    jd = JobDescriptionModel(
                        recruiter_id=recruiter_id,
                        short_title=job_role,
                        full_description=jd_text
                    )
                    db.add(jd)
                    db.commit()
                    db.refresh(jd)
                
                app = ApplicationModel(
                    candidate_id=new_cand.candidate_id,
                    jd_id=jd.jd_id,
                    status="CV_GENERATED"
                )
                db.add(app)
                db.commit()
                print(f"Created new candidate '{candidate_name}' (ID: {emp_id}) in DB for generated CV.")
    except Exception as e:
        db.rollback()
        print(f"Error saving generated CV to DB: {e}")
        raise e
    finally:
        db.close()


def migrate_filesystem_folders(recruiter_id):
    """Moves candidate files and embeddings on disk to recruiter-specific subfolders."""
    rec_id_str = str(recruiter_id)
    
    # 1. Migrate parsed_json/
    parsed_json_dir = "parsed_json"
    if os.path.exists(parsed_json_dir):
        rec_parsed_dir = os.path.join(parsed_json_dir, rec_id_str)
        os.makedirs(rec_parsed_dir, exist_ok=True)
        for item in os.listdir(parsed_json_dir):
            item_path = os.path.join(parsed_json_dir, item)
            if os.path.isfile(item_path) and item.endswith(".json") and item != "upload_stats.json":
                try:
                    shutil.move(item_path, os.path.join(rec_parsed_dir, item))
                except Exception as e:
                    print(f"Error moving parsed json {item}: {e}")
                    
    # 2. Migrate uploads/resumes/
    resumes_dir = "uploads/resumes"
    if os.path.exists(resumes_dir):
        rec_resumes_dir = os.path.join(resumes_dir, rec_id_str)
        os.makedirs(rec_resumes_dir, exist_ok=True)
        for item in os.listdir(resumes_dir):
            item_path = os.path.join(resumes_dir, item)
            if os.path.isfile(item_path) and not item.startswith("temp_"):
                try:
                    shutil.move(item_path, os.path.join(rec_resumes_dir, item))
                except Exception as e:
                    print(f"Error moving resume file {item}: {e}")
                    
    # 3. Migrate embeddings/
    embeddings_dir = "embeddings"
    if os.path.exists(embeddings_dir):
        rec_emb_dir = os.path.join(embeddings_dir, rec_id_str)
        os.makedirs(rec_emb_dir, exist_ok=True)
        
        emb_files = ["resume_index.faiss", "resume_mapping.json", "candidate_embeddings.json", "upload_stats.json"]
        for f in emb_files:
            f_path = os.path.join(embeddings_dir, f)
            if os.path.exists(f_path):
                try:
                    shutil.move(f_path, os.path.join(rec_emb_dir, f))
                except Exception as e:
                    print(f"Error moving embedding file {f}: {e}")


def run_db_migration(engine):
    """Safely migrates the database schema from old Candidates structure to normalized 5-table structure."""
    inspector = inspect(engine)
    if not inspector.has_table("candidates"):
        print("No candidates table found. Standard initialization will create the new schema.")
        return

    columns = [col["name"] for col in inspector.get_columns("candidates")]
    if "original_resume" in columns:
        print("Found old 'candidates' table. Starting DB and filesystem migration...")
        
        with engine.begin() as conn:
            conn.execute(text("RENAME TABLE candidates TO candidates_old"))
            print("Renamed table 'candidates' to 'candidates_old'.")
            
        Base.metadata.create_all(bind=engine)
        print("Created new normalized database tables.")
        
        db = SessionLocal()
        try:
            from services.auth_service import hash_password
            admin = db.query(RecruiterModel).filter(RecruiterModel.username == "admin").first()
            if not admin:
                pw_hash = hash_password("admin123")
                admin = RecruiterModel(
                    username="admin",
                    email="admin@example.com",
                    password_hash=pw_hash,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(admin)
                db.commit()
                db.refresh(admin)
                print("Default admin recruiter created.")
            
            admin_id = admin.recruiter_id
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM candidates_old"))
                rows = result.fetchall()
                
            print(f"Found {len(rows)} candidates to migrate.")
            
            for row in rows:
                row_dict = row._asdict()
                new_cand = CandidateModel(
                    recruiter_id=admin_id,
                    employee_id=row_dict["employee_id"],
                    candidate_name=row_dict.get("candidate_name"),
                    email=row_dict.get("email"),
                    phone=row_dict.get("phone"),
                    created_at=row_dict.get("uploaded_at") or datetime.utcnow(),
                    updated_at=row_dict.get("uploaded_at") or datetime.utcnow()
                )
                db.add(new_cand)
                db.commit()
                db.refresh(new_cand)
                
                if row_dict.get("original_resume") or row_dict.get("client_cv"):
                    new_doc = DocumentModel(
                        candidate_id=new_cand.candidate_id,
                        original_resume_blob=row_dict.get("original_resume"),
                        original_resume_filename=row_dict.get("original_resume_filename"),
                        generated_cv_blob=row_dict.get("client_cv"),
                        generated_cv_filename=row_dict.get("client_cv_filename"),
                        created_at=row_dict.get("uploaded_at") or datetime.utcnow(),
                        updated_at=row_dict.get("uploaded_at") or datetime.utcnow()
                    )
                    db.add(new_doc)
                    
                if row_dict.get("job_description"):
                    job_role = row_dict.get("job_role") or "Unknown Role"
                    new_jd = JobDescriptionModel(
                        recruiter_id=admin_id,
                        short_title=job_role,
                        full_description=row_dict["job_description"],
                        created_at=row_dict.get("uploaded_at") or datetime.utcnow(),
                        updated_at=row_dict.get("uploaded_at") or datetime.utcnow()
                    )
                    db.add(new_jd)
                    db.commit()
                    db.refresh(new_jd)
                    
                    app_status = "PARSED"
                    if row_dict.get("client_cv"):
                        app_status = "CV_GENERATED"
                    elif row_dict.get("job_description"):
                        app_status = "MATCHED"
                        
                    new_app = ApplicationModel(
                        candidate_id=new_cand.candidate_id,
                        jd_id=new_jd.jd_id,
                        similarity_score=None,
                        status=app_status,
                        created_at=row_dict.get("uploaded_at") or datetime.utcnow(),
                        updated_at=row_dict.get("uploaded_at") or datetime.utcnow()
                    )
                    db.add(new_app)
                    
                db.commit()
            
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE candidates_old"))
                print("Dropped old 'candidates_old' table.")
                
            migrate_filesystem_folders(admin_id)
            print("Database and Filesystem migration completed successfully!")
            
        except Exception as e:
            db.rollback()
            print(f"Error during migration: {e}")
            raise e
        finally:
            db.close()
