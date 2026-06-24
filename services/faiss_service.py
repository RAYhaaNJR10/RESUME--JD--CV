import faiss
import numpy as np
import json
import os


INDEX_PATH = "embeddings/resume_index.faiss"
MAPPING_PATH = "embeddings/resume_mapping.json"
CACHE_PATH = "embeddings/candidate_embeddings.json"


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

    candidate_name = candidate_data.get("candidate_name", "Unknown_Candidate")

    mapping.append(
        {
            "candidate_name":
                candidate_name,

            "resume_filename":
                candidate_data.get("resume_filename", ""),

            "current_role":
                candidate_data.get("current_role", "")
        }
    )

    save_index(index)
    save_mapping(mapping)

    # Save to candidate_embeddings.json cache
    try:
        cache = {}
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r") as f:
                cache = json.load(f)
        cache[candidate_name] = embedding
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"Error caching embedding in add_candidate: {e}")


def rebuild_index_from_parsed_json(parsed_json_folder="parsed_json"):
    index = create_index()
    mapping = []
    cache = {}

    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                cache = json.load(f)
        except Exception as e:
            print(f"Error loading cache: {e}")

    cache_modified = False

    if os.path.exists(parsed_json_folder):
        from services.embedding_service import create_embedding
        for filename in os.listdir(parsed_json_folder):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(parsed_json_folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    candidate = json.load(f)

                candidate_name = candidate.get("candidate_name", "Unknown_Candidate")
                embedding = cache.get(candidate_name)

                if not embedding:
                    search_profile = candidate.get("search_profile", "")
                    if not search_profile:
                        search_profile = candidate_name
                    embedding = create_embedding(search_profile)
                    cache[candidate_name] = embedding
                    cache_modified = True

                vector = normalize(embedding)
                index.add(vector)

                mapping.append({
                    "candidate_name": candidate_name,
                    "resume_filename": candidate.get("resume_filename", ""),
                    "current_role": candidate.get("current_role", "")
                })
            except Exception as e:
                print(f"Error indexing candidate file {filename}: {e}")

    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    save_index(index)
    save_mapping(mapping)

    if cache_modified:
        try:
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f, indent=4)
        except Exception as e:
            print(f"Error saving cache: {e}")

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