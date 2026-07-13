# 📄 Resume-JD-CV Platform

**An AI-powered recruitment tool that parses resumes, analyzes job descriptions, ranks candidates, and generates tailored CVs — built with FastAPI, OpenAI, and FAISS.**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991)
![FAISS](https://img.shields.io/badge/FAISS-Vector%20Search-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## 📌 Overview

Recruiters spend hours manually screening resumes against job descriptions. **Resume-JD-CV Platform** automates that pipeline end-to-end:

1. Upload a resume (PDF/DOCX) → AI extracts and structures the candidate's profile.
2. Upload or paste a Job Description → the system analyzes core requirements.
3. Candidates are embedded and ranked against the JD using **FAISS vector search**.
4. Recruiters can compare candidates side-by-side and auto-generate a **tailored CV** in DOCX format matched to the job.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🧠 **AI Resume Parsing** | Extracts text from PDF/DOCX and uses OpenAI to structure candidate profiles (skills, experience, education). |
| 📋 **JD Analysis** | Parses uploaded or pasted job descriptions to identify core requirements and keywords. |
| 🔍 **Semantic Candidate Ranking** | Uses embeddings + FAISS to rank candidates by relevance to a given JD. |
| ⚖️ **Candidate Comparison** | Side-by-side comparison view for shortlisting. |
| 📝 **Tailored CV Generation** | Auto-generates a DOCX CV customized to match a specific job description. |
| 🗄️ **Duplicate Detection** | Flags duplicate or near-duplicate resumes in the pipeline. |

---

## 🏗️ Architecture

```
┌──────────────┐      ┌──────────────┐      ┌───────────────────┐
│   Frontend    │ ───▶ │   FastAPI    │ ───▶ │   OpenAI API       │
│ (HTML/CSS/JS) │      │   (main.py)  │      │  (parsing, CV gen) │
└──────────────┘      └──────┬───────┘      └───────────────────┘
                              │
                 ┌────────────┼─────────────┐
                 ▼            ▼             ▼
          ┌───────────┐ ┌───────────┐ ┌────────────┐
          │ services/ │ │ embeddings/│ │   db.py    │
          │ (business │ │ (FAISS +   │ │ (SQLAlchemy│
          │  logic)   │ │  vectors)  │ │  models)   │
          └───────────┘ └───────────┘ └────────────┘
```

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, Python 3.8+
- **AI/ML:** OpenAI API (GPT-4o), FAISS for vector similarity search
- **Frontend:** HTML, CSS, JavaScript (vanilla)
- **Database:** SQLAlchemy (SQLite by default, MySQL optional)
- **Document Handling:** DOCX/PDF parsing and generation
- **Deployment:** Docker-ready

---

## 📂 Project Structure

```
.
├── main.py                  # FastAPI app entry point — routes & core API logic
├── db.py                    # Database configuration and SQLAlchemy models
├── build_index.py           # Builds the FAISS vector index from resume embeddings
├── requirements.txt         # Python dependencies
├── Dockerfile                # Container build configuration
├── frontend/                 # Static frontend (index.html, styles.css, app.js)
├── services/                  # Business logic: AI integration, doc processing, vector search
├── embeddings/                 # Embedding generation & FAISS index storage
├── test_cv_generation.py      # CV generation tests
├── test_embedding.py          # Embedding pipeline tests
├── test_matcher.py            # Candidate-JD matching tests
├── test_parser.py             # Resume parsing tests
├── test_search.py             # Vector search tests
└── profiling_log.txt          # Performance profiling notes
```

---

## ✅ Prerequisites

- Python 3.8+
- An **OpenAI API key** for AI parsing and CV generation
- *(Optional)* MySQL or another relational database — falls back to SQLite by default

---

## 🚀 Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/RAYhaaNJR10/RESUME--JD--CV.git
cd RESUME--JD--CV
```

### 2. Set up a virtual environment
```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Create a `.env` file in the root directory:
```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o
```

### 5. Build the vector index (optional, if using pre-existing resume data)
```bash
python build_index.py
```

### 6. Run the application
```bash
uvicorn main:app --reload
```

### 7. Access the app
- 🖥️ Frontend Dashboard: `http://127.0.0.1:8000/dashboard`
- 📑 API Docs (Swagger UI): `http://127.0.0.1:8000/docs`

---

## 🐳 Run with Docker

```bash
docker build -t resume-jd-cv .
docker run -p 8000:8000 --env-file .env resume-jd-cv
```

---

## 🧪 Testing

```bash
python test_cv_generation.py
python test_embedding.py
python test_matcher.py
python test_parser.py
python test_search.py
```

---

## 🗺️ Roadmap

- [ ] Add authentication for multi-recruiter access
- [ ] Support batch resume uploads
- [ ] Export candidate rankings as CSV/PDF reports
- [ ] Add support for additional file formats (RTF, plain text)

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome. Feel free to open a PR or issue.

---

## 📄 License

This project is licensed under the MIT License.

---

## 👤 Author

**Rayhaan** — AI/ML student & Data Science Intern, building tools at the intersection of AI and recruitment tech.
