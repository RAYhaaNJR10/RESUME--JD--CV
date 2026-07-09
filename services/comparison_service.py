import json
import os
import re


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "we",
    "you",
}


def compare_candidates(
    candidate_names,
    jd_text,
    parsed_json_folder="parsed_json"
):
    comparisons = []
    missing_candidates = []

    for candidate_name in candidate_names:

        candidate = load_candidate(
            candidate_name,
            parsed_json_folder
        )

        if not candidate:
            missing_candidates.append(
                candidate_name
            )
            continue

        comparisons.append(
            build_candidate_comparison(
                candidate,
                jd_text
            )
        )

    comparisons.sort(
        key=lambda item: item["match_score"],
        reverse=True
    )

    return {
        "count": len(comparisons),
        "missing_candidates": missing_candidates,
        "results": comparisons
    }


def load_candidate(
    candidate_name,
    parsed_json_folder
):
    if not os.path.exists(
        parsed_json_folder
    ):
        return None

    exact_path = os.path.join(
        parsed_json_folder,
        f"{candidate_name}.json"
    )

    if os.path.exists(
        exact_path
    ):
        return load_json(
            exact_path
        )

    requested_name = normalize_name(
        candidate_name
    )

    for root, dirs, files in os.walk(parsed_json_folder):
        for filename in files:
            if not filename.endswith(".json"):
                continue

            file_path = os.path.join(
                root,
                filename
            )

            candidate = load_json(
                file_path
            )

            if not candidate:
                continue

            candidate_profile_name = normalize_name(
                candidate.get(
                    "candidate_name",
                    ""
                )
            )

            filename_name = normalize_name(
                os.path.splitext(
                    filename
                )[0]
            )

            if (
                requested_name == candidate_profile_name
                or requested_name == filename_name
                or requested_name in candidate_profile_name
                or requested_name in filename_name
            ):
                return candidate

    return None


def load_json(
    file_path
):
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return None


def build_candidate_comparison(
    candidate,
    jd_text
):
    key_skills = candidate.get(
        "skills",
        []
    )

    domains = candidate.get(
        "domains",
        []
    )

    education = candidate.get(
        "education",
        []
    )

    return {
        "candidate_name": candidate.get(
            "candidate_name",
            ""
        ),
        "current_role": candidate.get(
            "current_role",
            ""
        ),
        "years_of_experience": candidate.get(
            "years_of_experience",
            0
        ),
        "match_score": calculate_match_score(
            candidate,
            jd_text
        ),
        "key_skills": prioritize_skills(
            key_skills,
            jd_text
        ),
        "domains": domains,
        "education": education,
        "strengths": infer_strengths(
            candidate
        ),
        "projects": candidate.get("projects", []),
        "about_candidate": candidate.get("about_candidate", "")
    }


def calculate_match_score(
    candidate,
    jd_text
):
    jd_terms = tokenize(
        jd_text
    )

    if not jd_terms:
        return 0

    candidate_terms = tokenize(
        build_search_text(
            candidate
        )
    )

    matched_terms = jd_terms.intersection(
        candidate_terms
    )

    return round(
        (len(matched_terms) / len(jd_terms)) * 100,
        2
    )


def prioritize_skills(
    skills,
    jd_text,
    limit=12
):
    jd_terms = tokenize(
        jd_text
    )

    matching_skills = []
    other_skills = []

    for skill in skills:

        skill_terms = tokenize(
            str(skill)
        )

        if skill_terms.intersection(
            jd_terms
        ):
            matching_skills.append(
                skill
            )
        else:
            other_skills.append(
                skill
            )

    return (
        matching_skills
        + other_skills
    )[:limit]


def infer_strengths(
    candidate
):
    strengths = []

    years_of_experience = candidate.get(
        "years_of_experience",
        0
    )

    if years_of_experience:
        strengths.append(
            f"{years_of_experience}+ years of relevant experience"
        )

    current_role = candidate.get(
        "current_role",
        ""
    )

    if current_role:
        strengths.append(
            f"Current role exposure as {current_role}"
        )

    domains = candidate.get(
        "domains",
        []
    )

    if domains:
        strengths.append(
            f"Domain exposure in {', '.join(domains[:3])}"
        )

    experience = candidate.get(
        "experience",
        []
    )

    if len(experience) > 1:
        strengths.append(
            f"Experience across {len(experience)} roles or projects"
        )

    skills = candidate.get(
        "skills",
        []
    )

    if skills:
        strengths.append(
            f"Hands-on skills include {', '.join(skills[:5])}"
        )

    return strengths[:5]


def build_search_text(
    candidate
):
    values = [
        candidate.get(
            "candidate_name",
            ""
        ),
        candidate.get(
            "current_role",
            ""
        ),
        candidate.get(
            "search_profile",
            ""
        ),
        " ".join(
            candidate.get(
                "skills",
                []
            )
        ),
        " ".join(
            candidate.get(
                "domains",
                []
            )
        ),
    ]

    for experience in candidate.get(
        "experience",
        []
    ):
        values.extend(
            [
                experience.get(
                    "company",
                    ""
                ),
                experience.get(
                    "project",
                    ""
                ),
                experience.get(
                    "role",
                    ""
                ),
                " ".join(
                    experience.get(
                        "technologies",
                        []
                    )
                ),
                " ".join(
                    experience.get(
                        "responsibilities",
                        []
                    )
                ),
            ]
        )

    for project in candidate.get(
        "projects",
        []
    ):
        values.extend(
            [
                project.get(
                    "name",
                    ""
                ),
                project.get(
                    "description",
                    ""
                ),
                " ".join(
                    project.get(
                        "technologies",
                        []
                    )
                ),
            ]
        )

    return " ".join(
        values
    )


def tokenize(
    text
):
    terms = set()

    for term in re.findall(
        r"[A-Za-z0-9+#.]+",
        str(text).lower()
    ):

        if (
            len(term) < 2
            or term in STOP_WORDS
        ):
            continue

        terms.add(
            term
        )

    return terms


def normalize_name(
    name
):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(name).lower()
    )
