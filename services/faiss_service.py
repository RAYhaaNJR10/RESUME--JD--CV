import faiss
import numpy as np
import json
import os

def get_paths(recruiter_id):
    if recruiter_id is not None:
        base_dir = f"embeddings/{recruiter_id}"
    else:
        base_dir = "embeddings"
    os.makedirs(base_dir, exist_ok=True)
    return {
        "index": os.path.join(base_dir, "resume_index.faiss"),
        "mapping": os.path.join(base_dir, "resume_mapping.json"),
        "cache": os.path.join(base_dir, "candidate_embeddings.json")
    }

def create_index(dimension=1536):
    return faiss.IndexFlatIP(dimension)

def normalize(vector):
    vector = np.array(vector, dtype=np.float32)
    vector = vector.reshape(1, -1)
    faiss.normalize_L2(vector)
    return vector

def save_index(index, recruiter_id=None):
    paths = get_paths(recruiter_id)
    faiss.write_index(index, paths["index"])

def load_index(recruiter_id=None):
    paths = get_paths(recruiter_id)
    if not os.path.exists(paths["index"]):
        return create_index()
    return faiss.read_index(paths["index"])

def save_mapping(mapping, recruiter_id=None):
    paths = get_paths(recruiter_id)
    with open(paths["mapping"], "w") as f:
        json.dump(mapping, f, indent=4)

def load_mapping(recruiter_id=None):
    paths = get_paths(recruiter_id)
    if not os.path.exists(paths["mapping"]):
        return []
    with open(paths["mapping"], "r") as f:
        return json.load(f)

def add_candidate(candidate_data, embedding, recruiter_id=None):
    index = load_index(recruiter_id)
    mapping = load_mapping(recruiter_id)
    vector = normalize(embedding)
    index.add(vector)

    candidate_name = candidate_data.get("candidate_name", "Unknown_Candidate")
    mapping.append({
        "candidate_name": candidate_name,
        "resume_filename": candidate_data.get("resume_filename", ""),
        "current_role": candidate_data.get("current_role", "")
    })

    save_index(index, recruiter_id)
    save_mapping(mapping, recruiter_id)

    # Save to candidate_embeddings.json cache
    paths = get_paths(recruiter_id)
    try:
        cache = {}
        if os.path.exists(paths["cache"]):
            with open(paths["cache"], "r") as f:
                cache = json.load(f)
        cache[candidate_name] = embedding
        with open(paths["cache"], "w") as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"Error caching embedding in add_candidate: {e}")

def _get_all_json_files(folder_path, recursive=False):
    json_files = []
    if not os.path.exists(folder_path):
        return json_files
    if recursive:
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                if filename.endswith(".json") and filename != "upload_stats.json" and filename != "active_template.json":
                    json_files.append((os.path.join(root, filename), filename))
    else:
        for filename in os.listdir(folder_path):
            if filename.endswith(".json") and filename != "upload_stats.json" and filename != "active_template.json":
                json_files.append((os.path.join(folder_path, filename), filename))
    return json_files

def rebuild_index_from_parsed_json(parsed_json_folder=None, recruiter_id=None):
    if parsed_json_folder is None:
        parsed_json_folder = f"parsed_json/{recruiter_id}" if recruiter_id is not None else "parsed_json"
        
    index = create_index()
    mapping = []
    cache = {}
    paths = get_paths(recruiter_id)

    if os.path.exists(paths["cache"]):
        try:
            with open(paths["cache"], "r") as f:
                cache = json.load(f)
        except Exception as e:
            print(f"Error loading cache: {e}")

    cache_modified = False

    json_files = _get_all_json_files(parsed_json_folder, recursive=(recruiter_id is None))
    if json_files:
        from services.embedding_service import create_embedding
        for file_path, filename in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    candidate = json.load(f)

                candidate_name = candidate.get("candidate_name", "Unknown_Candidate")
                cache_key = filename
                embedding = cache.get(cache_key)

                if not embedding:
                    embedding = cache.get(candidate_name)
                    if not embedding:
                        search_profile = candidate.get("search_profile", "")
                        if not search_profile:
                            search_profile = candidate_name
                        embedding = create_embedding(search_profile)
                        cache[candidate_name] = embedding
                    cache[cache_key] = embedding
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

    save_index(index, recruiter_id)
    save_mapping(mapping, recruiter_id)

    if cache_modified:
        try:
            with open(paths["cache"], "w") as f:
                json.dump(cache, f, indent=4)
        except Exception as e:
            print(f"Error saving cache: {e}")

def search_candidates(query_embedding, top_k=10, recruiter_id=None):
    index = load_index(recruiter_id)
    mapping = load_mapping(recruiter_id)
    query = normalize(query_embedding)
    scores, indices = index.search(query, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        if idx < len(mapping):
            candidate = mapping[idx].copy()
            candidate["score"] = float(score)
            results.append(candidate)
    return results

def rebuild_index_from_json(parsed_json_dir=None, recruiter_id=None):
    if parsed_json_dir is None:
        parsed_json_dir = f"parsed_json/{recruiter_id}" if recruiter_id is not None else "parsed_json"
        
    from services.embedding_service import create_embedding

    index = create_index()
    mapping = []

    json_files = _get_all_json_files(parsed_json_dir, recursive=(recruiter_id is None))
    if not json_files:
        save_index(index, recruiter_id)
        save_mapping(mapping, recruiter_id)
        return

    for file_path, filename in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                candidate = json.load(f)

            if "embedding" not in candidate:
                search_profile = candidate.get("search_profile", "")
                if search_profile:
                    embedding = create_embedding(search_profile)
                    candidate["embedding"] = embedding
                    with open(file_path, "w", encoding="utf-8") as fw:
                        json.dump(candidate, fw, indent=4, ensure_ascii=False)
                else:
                    continue

            embedding = candidate["embedding"]
            vector = normalize(embedding)
            index.add(vector)

            mapping.append({
                "candidate_name": candidate.get("candidate_name", "Unknown_Candidate"),
                "resume_filename": candidate.get("resume_filename", filename.replace(".json", ".pdf")),
                "current_role": candidate.get("current_role", "")
            })
        except Exception as e:
            print(f"Error indexing {filename}: {e}")

    save_index(index, recruiter_id)
    save_mapping(mapping, recruiter_id)
