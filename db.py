import os
import re
import json
import threading
from datetime import datetime
from dotenv import load_dotenv

# Ensure env variables are loaded before reading
load_dotenv()

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, LargeBinary
from sqlalchemy.engine import URL
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
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

class CandidateModel(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(20), unique=True, nullable=False)
    candidate_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    job_role = Column(String(50), nullable=True)
    job_description = Column(Text, nullable=True)
    original_resume = Column(LargeBinary().with_variant(LONGBLOB, "mysql"), nullable=True)
    original_resume_filename = Column(String(255), nullable=True)
    client_cv = Column(LargeBinary().with_variant(LONGBLOB, "mysql"), nullable=True)
    client_cv_filename = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, nullable=True)
    generated_at = Column(DateTime, nullable=True)


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
    # Look for common phone patterns: 10-12 digits, optional +, -, spaces, parens
    match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+?\d{10,12}', text)
    return match.group(0).strip() if match else ""


def extract_job_role(jd_text: str) -> str:
    """Extract a short, recruiter-friendly label for the job role from the JD."""
    if not jd_text:
        return "Unknown Role"
    lines = [line.strip() for line in jd_text.split('\n') if line.strip()]
    
    # Try to find common title tags
    for line in lines[:3]:
        match = re.search(r'(?:role|title|position|job)\s*:\s*(.+)', line, re.IGNORECASE)
        if match:
            return match.group(1)[:50].strip()
            
    # Fallback to the first line if no title tags are found
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
    latest = db_session.query(CandidateModel).order_by(CandidateModel.id.desc()).first()
    if latest and latest.employee_id.startswith("EMP"):
        try:
            num = int(latest.employee_id[3:])
            return f"EMP{num + 1:04d}"
        except ValueError:
            pass
    
    # Fallback: Count rows
    count = db_session.query(CandidateModel).count()
    return f"EMP{count + 1:04d}"


def save_generated_cv_to_db(candidate_name: str, docx_path: str, jd_text: str):
    """Saves generated DOCX bytes and JD summary to the database, updating the candidate record."""
    if not os.path.exists(docx_path):
        return

    with open(docx_path, "rb") as f:
        docx_bytes = f.read()

    filename = os.path.basename(docx_path)
    job_role = extract_job_role(jd_text)
    job_description = extract_job_description_summary(jd_text)

    db = SessionLocal()
    try:
        with db_session_lock:
            db_candidate = db.query(CandidateModel).filter(CandidateModel.candidate_name == candidate_name).first()
            if db_candidate:
                db_candidate.client_cv = docx_bytes
                db_candidate.client_cv_filename = filename
                db_candidate.job_role = job_role
                db_candidate.job_description = job_description
                db_candidate.generated_at = datetime.utcnow()
                db.commit()
                print(f"Updated CV for candidate '{candidate_name}' (ID: {db_candidate.employee_id}) in DB.")
            else:
                # If candidate name doesn't exist, create a new record
                emp_id = get_next_employee_id(db)
                new_cand = CandidateModel(
                    employee_id=emp_id,
                    candidate_name=candidate_name,
                    client_cv=docx_bytes,
                    client_cv_filename=filename,
                    job_role=job_role,
                    job_description=job_description,
                    generated_at=datetime.utcnow(),
                    uploaded_at=datetime.utcnow()
                )
                db.add(new_cand)
                db.commit()
                print(f"Created new candidate '{candidate_name}' (ID: {emp_id}) in DB for generated CV.")
    except Exception as e:
        db.rollback()
        print(f"Error saving generated CV to DB: {e}")
        raise e
    finally:
        db.close()
