from services.embedding_service import create_embedding
from services.faiss_service import search_candidates


def match_candidates(
    jd_text,
    top_k=100,
    recruiter_id=None
):

    jd_embedding = create_embedding(
        jd_text
    )

    results = search_candidates(
        jd_embedding,
        top_k,
        recruiter_id
    )

    return results