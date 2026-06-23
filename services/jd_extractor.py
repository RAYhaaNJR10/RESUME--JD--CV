from pypdf import PdfReader
from docx import Document


def extract_text_from_pdf(file_path):
    text = ""

    reader = PdfReader(file_path)

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text.strip()


def extract_text_from_docx(file_path):
    doc = Document(file_path)

    text = []

    for para in doc.paragraphs:

        if para.text:
            text.append(
                para.text
            )

    return "\n".join(text).strip()


def extract_text_from_txt(file_path):
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:
            return f.read().strip()

    except UnicodeDecodeError:
        with open(
            file_path,
            "r",
            encoding="latin-1"
        ) as f:
            return f.read().strip()


def extract_jd_text(file_path):
    lower_path = file_path.lower()

    if lower_path.endswith(".pdf"):
        text = extract_text_from_pdf(
            file_path
        )

    elif lower_path.endswith(".docx"):
        text = extract_text_from_docx(
            file_path
        )

    elif lower_path.endswith(".txt"):
        text = extract_text_from_txt(
            file_path
        )

    else:
        raise ValueError(
            "Unsupported JD file type. Supported file types: PDF, DOCX, TXT"
        )

    if not text:
        raise ValueError(
            "JD file is empty or no text could be extracted"
        )

    return text
