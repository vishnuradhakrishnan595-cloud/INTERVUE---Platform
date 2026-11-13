"""Resume text extraction and structured parsing (heuristics, optionally refined by an LLM)."""
import re
from datetime import date

from . import llm
from .skills import canonicalize_list, extract_skills

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s\-()]{8,}\d)(?!\d)")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w.-]+\.[a-z]{2,}(?:/[\w\-./?%&=#]*)?", re.I)
EXPLICIT_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.I)
RANGE_RE = re.compile(r"((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:19|20)\d{2}|present|current|now)", re.I)
DEGREE_RE = re.compile(
    r"\b(ph\.?d|doctorate|master|mba|m\.?tech|m\.?sc|mca|m\.?e|bachelor|b\.?tech|b\.?e|b\.?sc|bca|b\.?com|diploma)\b", re.I)

HEADERS = {
    "education": "education", "academic background": "education", "qualifications": "education",
    "experience": "experience", "work experience": "experience", "professional experience": "experience",
    "employment history": "experience", "projects": "projects", "personal projects": "projects",
    "certifications": "certifications", "certificates": "certifications", "skills": "skills",
    "technical skills": "skills", "summary": "summary", "profile": "summary", "objective": "summary",
}


def extract_text(file_obj, filename: str = "") -> str:
    """Extract plain text from a PDF, DOCX or TXT file-like object."""
    name = (filename or getattr(file_obj, "name", "")).lower()
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(file_obj).pages)
        if name.endswith(".docx"):
            import docx
            d = docx.Document(file_obj)
            parts = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            return "\n".join(parts)
        data = file_obj.read()
        return data.decode("utf-8", "ignore") if isinstance(data, bytes) else str(data)
    finally:
        if hasattr(file_obj, "seek"):
            try:
                file_obj.seek(0)
            except Exception:
                pass


def _split_sections(text: str):
    sections, current = {}, "header"
    for line in text.splitlines():
        key = line.strip().rstrip(":").lower()
        if key in HEADERS:
            current = HEADERS[key]
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line.strip())
    return {k: [l for l in v if l] for k, v in sections.items()}


def _experience_years(text: str) -> float:
    explicit = [float(m) for m in EXPLICIT_YEARS_RE.findall(text) if float(m) <= 40]
    if explicit:
        return max(explicit)
    total, this_year = 0.0, date.today().year
    for start, end in RANGE_RE.findall(text):
        end_y = this_year if end.lower() in ("present", "current", "now") else int(end)
        if int(start) <= end_y:
            total += end_y - int(start)
    return min(total, 40.0)


def parse_resume_text(text: str, use_llm: bool = True) -> dict:
    text = text or ""
    sections = _split_sections(text)
    header_lines = sections.get("header", [])
    email_m = EMAIL_RE.search(text)
    email = email_m.group(0) if email_m else ""
    phone_m = PHONE_RE.search(text)
    name = next((l for l in header_lines[:5] if 2 <= len(l.split()) <= 4 and not re.search(r"[\d@]", l)), "")

    edu = sections.get("education") or [l for l in text.splitlines() if DEGREE_RE.search(l)]
    skills = extract_skills(text)
    links = {"github": "", "linkedin": "", "portfolio": ""}
    for m in URL_RE.findall(text):
        low = m.lower()
        if "github.com" in low and not links["github"]:
            links["github"] = m
        elif "linkedin.com" in low and not links["linkedin"]:
            links["linkedin"] = m

    parsed = {
        "name": name,
        "email": email,
        "phone": phone_m.group(1).strip() if phone_m else "",
        "skills": skills,
        "education": edu[:6],
        "experience_years": _experience_years(text),
        "experience": sections.get("experience", [])[:15],
        "projects": sections.get("projects", [])[:15],
        "certifications": sections.get("certifications", [])[:10],
        "links": links,
        "parser": "heuristic",
    }

    if use_llm and llm.llm_available() and text.strip():
        refined = llm.llm_json(
            "You are a resume parser. Return JSON with keys: name, email, phone, skills (list of strings), "
            "education (list of strings), experience_years (number), experience (list of strings), "
            "projects (list of strings), certifications (list of strings).",
            text[:12000],
        )
        if isinstance(refined, dict):
            for k in ("name", "email", "phone", "education", "experience", "projects", "certifications"):
                if refined.get(k):
                    parsed[k] = refined[k]
            if isinstance(refined.get("experience_years"), (int, float)):
                parsed["experience_years"] = float(refined["experience_years"])
            parsed["skills"] = canonicalize_list(list(parsed["skills"]) + list(refined.get("skills") or []))
            parsed["parser"] = "llm+heuristic"
    return parsed
