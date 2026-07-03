from pypdf import PdfReader
from docx import Document


def extract_pdf_text(file_path):
    text = ""

    reader = PdfReader(file_path)

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text


def extract_docx_text(file_path):
    """
    Extract ALL text from a DOCX file, including content inside:
    - Normal paragraphs
    - Tables
    - Text boxes (w:txbxContent)
    - Content controls (w:sdtContent)
    - Headers and Footers
    - Shapes and drawing objects

    Uses low-level XML iteration over w:t elements to ensure nothing is missed.
    The naive doc.paragraphs approach only reads body-level <w:p> elements
    and silently drops text inside the structures listed above.
    """
    doc = Document(file_path)

    WP_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    T_TAG = f"{WP_NS}t"
    P_TAG = f"{WP_NS}p"

    def _collect_paragraphs_from_element(element):
        """Walk all <w:p> elements under a given XML element and join
        the <w:t> runs within each paragraph, preserving paragraph breaks."""
        paragraphs = []
        for p_elem in element.iter(P_TAG):
            runs = []
            for t_elem in p_elem.iter(T_TAG):
                if t_elem.text:
                    runs.append(t_elem.text)
            line = "".join(runs).strip()
            if line:
                paragraphs.append(line)
        return paragraphs

    # 1. Extract from the document body (paragraphs, tables, text boxes, etc.)
    all_paragraphs = _collect_paragraphs_from_element(doc.element.body)

    # 2. Extract from headers and footers (if present)
    for section in doc.sections:
        for header_footer in [section.header, section.footer]:
            if header_footer and header_footer.is_linked_to_previous is False:
                hf_paras = _collect_paragraphs_from_element(header_footer._element)
                all_paragraphs.extend(hf_paras)

    return "\n".join(all_paragraphs)


def extract_text(file_path):
    if file_path.lower().endswith(".pdf"):
        return extract_pdf_text(file_path)

    elif file_path.lower().endswith(".docx"):
        return extract_docx_text(file_path)

    raise Exception("Unsupported file format")