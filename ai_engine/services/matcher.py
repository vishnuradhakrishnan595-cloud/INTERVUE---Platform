"""Job <-> candidate matching: skill, experience and education scores (0-100)."""
import re

from .skills import canonicalize_list

WEIGHTS = {"skills": 0.60, "experience": 0.25, "education": 0.15}

_DEGREE_PATTERNS = [
    (5, re.compile(r"\b(ph\.?d|doctorate)\b", re.I)),
    (4, re.compile(r"\b(master|mba|m\.?tech|m\.?sc|mca|m\.?e)\b", re.I)),
    (3, re.compile(r"\b(bachelor|b\.?tech|b\.?e|b\.?sc|bca|b\.?com)\b", re.I)),
    (2, re.compile(r"\bdiploma\b", re.I)),
    (1, re.compile(r"\b(high school|12th|hsc|secondary)\b", re.I)),
]


def degree_rank(text) -> int:
    if isinstance(text, (list, tuple)):
        text = " ".join(map(str, text))
    text = str(text or "")
    return max([rank for rank, pat in _DEGREE_PATTERNS if pat.search(text)] or [0])


def _pct(num, den) -> float:
    return round(100.0 * num / den, 1) if den else 100.0


def compute_match(job: dict, candidate: dict) -> dict:
    """
    job:       {required_skills, preferred_skills, experience_min, education}
    candidate: {skills, experience_years, education}
    """
    req = canonicalize_list(job.get("required_skills"))
    pref = canonicalize_list(job.get("preferred_skills"))
    have = {s.lower() for s in canonicalize_list(candidate.get("skills"))}

    matched_req = [s for s in req if s.lower() in have]
    missing_req = [s for s in req if s.lower() not in have]
    matched_pref = [s for s in pref if s.lower() in have]

    req_score = _pct(len(matched_req), len(req))
    skill_score = round(0.8 * req_score + 0.2 * _pct(len(matched_pref), len(pref)), 1) if pref else req_score

    years = float(candidate.get("experience_years") or 0)
    exp_min = float(job.get("experience_min") or 0)
    exp_score = 100.0 if exp_min <= 0 else round(min(100.0, 100.0 * years / exp_min), 1)

    need, got = degree_rank(job.get("education")), degree_rank(candidate.get("education"))
    edu_score = 100.0 if need == 0 else round(min(100.0, 100.0 * got / need), 1) if got else 40.0

    overall = round(skill_score * WEIGHTS["skills"] + exp_score * WEIGHTS["experience"]
                    + edu_score * WEIGHTS["education"], 1)

    parts = [f"Matches {len(matched_req)}/{len(req)} required skills" if req else "No required skills specified"]
    if missing_req:
        parts.append("missing: " + ", ".join(missing_req))
    parts.append(f"{years:g} yrs experience vs {exp_min:g} required")
    return {
        "skill_match": skill_score,
        "experience_match": exp_score,
        "education_match": edu_score,
        "overall_match": overall,
        "matched_skills": matched_req + matched_pref,
        "missing_skills": missing_req,
        "summary": "; ".join(parts) + ".",
    }
