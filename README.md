# Resume JD CV Platform

A platform designed to parse resumes, match candidates against job descriptions (JD), and generate tailored CVs using OpenAI, FAISS, and FastAPI.

## Features

- **Resume Parsing:** Upload and parse resumes (PDF, DOCX) to extract structured candidate data.
- **JD Processing:** Upload and extract text from Job Descriptions.
- **Candidate Matching & Ranking:** Rank parsed resumes against a Job Description using text embeddings and FAISS similarity search.
- **Candidate Comparison:** Compare multiple candidates side-by-side based on their fit for a specific JD.
- **CV Generation:** Automatically generate tailored DOCX resumes for candidates aligned to the job description.
- **Template Management:** Upload and manage custom DOCX templates for CV generation.
- **Recruiter Dashboard:** A built-in frontend interface for recruiters to manage the workflow.

## Technology Stack

- **Backend:** Python, FastAPI, FAISS, OpenAI API
- **Document Processing:** `pypdf`, `python-docx`
- **Frontend:** HTML, CSS, JavaScript (served statically via FastAPI)

## Setup & Installation

### Prerequisites

- Python 3.9+
- An OpenAI API key

### Installation Steps

1. Clone the repository and navigate to the project directory:
   ```bash
   # cd your-repo
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the root directory and add your OpenAI API key:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   ```

## Running the Application

Start the FastAPI server using Uvicorn:

```bash
uvicorn main:app --reload
```

The application will be accessible at:
- **API Documentation (Swagger UI):** `http://localhost:8000/docs`
- **Recruiter Dashboard:** `http://localhost:8000/dashboard/`

## Project Structure

- `main.py` - FastAPI application entry point, containing all API endpoints.
- `build_index.py` - Script to rebuild the FAISS index from parsed JSONs.
- `services/` - Contains core business logic modules:
  - `parser.py`, `extractor.py`, `jd_extractor.py` - Document extraction and parsing.
  - `matcher.py`, `comparison_service.py` - Candidate matching and comparison logic.
  - `faiss_service.py`, `faiss_index.py`, `embedding_service.py` - Vector search and embedding operations.
  - `openai_service.py` - Interfacing with OpenAI.
  - `cv_generator.py`, `docx_generator.py` - Generation of tailored DOCX files.
- `frontend/` - Static files (HTML, CSS, JS) for the recruiter dashboard.
- `tests/` - Test files (e.g. `test_cv_generation.py`, `test_matcher.py`, etc.).

## Key API Endpoints

- `GET /` - Check if the platform is running.
- `POST /upload-resumes` - Upload multiple resumes (PDF/DOCX) for parsing and indexing.
- `GET /candidates` - List all parsed candidates.
- `GET /candidate/{candidate_name}` - Retrieve detailed JSON for a specific candidate.
- `POST /upload-jd` - Upload and extract text from a JD file.
- `POST /rank-candidates` - Rank candidates against provided JD text.
- `POST /compare-candidates` - Compare selected candidates for a JD.
- `POST /generate-selected-cvs` - Generate tailored CVs (as a ZIP file) for selected candidates.
- `POST /upload-template` - Upload a custom `.docx` template for generated CVs.
- `GET /active-template` - Get information about the currently active template.
- `DELETE /active-template` - Delete the custom template and revert to the default.
