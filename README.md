# Resume JD CV Platform

A comprehensive platform designed to streamline the recruitment process by parsing candidate resumes, analyzing job descriptions (JD), and generating tailored CVs. Built with a FastAPI backend and a clean, responsive HTML/CSS/JS frontend.

## Key Features

- **Resume Upload & AI Parsing:** Upload resumes in PDF or DOCX formats. The system extracts text and uses AI (OpenAI) to intelligently parse and structure the candidate's profile.
- **Job Description (JD) Analysis:** Upload or paste Job Descriptions to analyze core requirements.
- **Candidate Ranking & Matching:** Employs advanced vector search (FAISS) and embeddings to rank candidates against a given Job Description, ensuring the best fit.
- **Candidate Comparison:** Compare multiple candidates side-by-side to make informed decisions.
- **Tailored CV Generation:** Automatically generate bespoke CVs in DOCX format tailored specifically to the requirements of the job description.

## Project Structure

- `main.py`: The FastAPI application entry point containing routes and core API logic.
- `frontend/`: Contains the static frontend files (`index.html`, `styles.css`, `app.js`).
- `services/`: Encapsulates business logic, including AI integrations, document processing, and vector search.
- `db.py`: Database configuration and SQLAlchemy models.
- `requirements.txt`: Python package dependencies.

## Prerequisites

- Python 3.8+
- An OpenAI API Key for AI parsing and CV generation.
- MySQL database (Required, as SQLite fallback has been removed).

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository_url>
cd <repository_directory>
```

### 2. Set Up a Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the root directory (or export the variables in your shell) and add the following:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o  # or your preferred model

# Database Configuration (MySQL)
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=resume_platform
DB_USER=root
DB_PASSWORD=root

# Authentication
JWT_SECRET_KEY=super-secret-key-change-me-123456
```

### 5. Start the Application

Run the FastAPI backend using `uvicorn`:

```bash
uvicorn main:app --reload
```

### 6. Access the Application

Once the server is running, open your browser and navigate to:

- Login Page: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login) (Default credentials: `admin` / `admin123`)
- Frontend Dashboard: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
- API Documentation (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Testing

The project includes various test scripts at the root level. Ensure you have the proper environment variables set, then run the tests:

```bash
python test_cv_generation.py
python test_embedding.py
python test_matcher.py
python test_parser.py
python test_search.py
```
