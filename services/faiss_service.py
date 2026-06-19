import faiss
import numpy as np
import json
import os


INDEX_PATH = "embeddings/resume_index.faiss"
MAPPING_PATH = "embeddings/resume_mapping.json"


def create_index(dimension=1536):
    return faiss.IndexFlatIP(dimension)


def normalize(vector):
    vector = np.array(vector, dtype=np.float32)
    vector = vector.reshape(1, -1)

    faiss.normalize_L2(vector)

    return vector


def save_index(index):
    faiss.write_index(index, INDEX_PATH)


def load_index():

    if not os.path.exists(INDEX_PATH):
        return create_index()

    return faiss.read_index(INDEX_PATH)


def save_mapping(mapping):

    with open(MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=4)


def load_mapping():

    if not os.path.exists(MAPPING_PATH):
        return []

    with open(MAPPING_PATH, "r") as f:
        return json.load(f)


def add_candidate(candidate_data, embedding):

    index = load_index()

    mapping = load_mapping()

    vector = normalize(embedding)

    index.add(vector)

    mapping.append(
        {
            "candidate_name":
                candidate_data["candidate_name"],

            "resume_filename":
                candidate_data["resume_filename"],

            "current_role":
                candidate_data["current_role"]
        }
    )

    save_index(index)
    save_mapping(mapping)


def search_candidates(query_embedding, top_k=10):

    index = load_index()

    mapping = load_mapping()

    query = normalize(query_embedding)

    scores, indices = index.search(
        query,
        top_k
    )

    results = []

    for score, idx in zip(
        scores[0],
        indices[0]
    ):

        if idx == -1:
            continue

        candidate = mapping[idx]

        candidate["score"] = float(score)

        results.append(candidate)

    return results