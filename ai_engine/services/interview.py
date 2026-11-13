"""AI interview engine: question generation, adaptive follow-ups and answer analysis.

Every function tries the configured LLM first and falls back to deterministic heuristics so the
platform works offline. Scores are decision-support signals for humans, never final verdicts.
"""
import random
import re

from . import llm
from .skills import canonicalize_list, extract_skills

DIFFICULTIES = ["easy", "medium", "hard"]

# skill -> difficulty -> [(question, [expected keywords])]
BANK = {
    "Python": {
        "easy": [("What is the difference between a list and a tuple in Python?", ["mutable", "immutable", "tuple", "list"])],
        "medium": [("Explain decorators and generators and when you would use each.", ["decorator", "function", "yield", "generator", "iterator"])],
        "hard": [("How does the GIL affect multi-threaded Python programs and how do you work around it?", ["gil", "thread", "process", "multiprocessing", "asyncio"])],
    },
    "Django": {
        "easy": [("Explain Django's MVT architecture.", ["model", "view", "template", "url"])],
        "medium": [("How does the Django ORM work and how do you avoid the N+1 query problem?", ["queryset", "select_related", "prefetch_related", "lazy", "query"])],
        "hard": [("How would you optimise a slow Django API endpoint under heavy load?", ["cache", "index", "select_related", "pagination", "profiling", "query"])],
    },
    "Django REST Framework": {
        "easy": [("What are serializers in DRF and why are they needed?", ["serializer", "validation", "json", "model"])],
        "medium": [("Explain permissions, authentication and throttling in DRF.", ["permission", "authentication", "throttle", "jwt", "token"])],
        "hard": [("How would you design versioned, paginated and secure REST APIs with DRF at scale?", ["version", "pagination", "throttle", "cache", "permission"])],
    },
    "REST API": {
        "easy": [("Explain what a REST API is.", ["http", "resource", "stateless", "json"])],
        "medium": [("What is the difference between PUT and PATCH?", ["replace", "partial", "idempotent", "update"])],
        "hard": [("How do you design idempotent and backward-compatible REST endpoints?", ["idempotent", "version", "key", "retry", "compatible"])],
    },
    "React": {
        "easy": [("What is the virtual DOM in React?", ["virtual", "dom", "diff", "render"])],
        "medium": [("Explain useEffect and common pitfalls with its dependency array.", ["effect", "dependency", "cleanup", "render", "stale"])],
        "hard": [("How would you diagnose and fix performance problems in a large React app?", ["memo", "profiler", "rerender", "usememo", "usecallback", "lazy"])],
    },
    "PostgreSQL": {
        "easy": [("What is the difference between a primary key and a foreign key?", ["unique", "reference", "table", "constraint"])],
        "medium": [("How do indexes work and when can they hurt performance?", ["index", "b-tree", "write", "scan", "query"])],
        "hard": [("Explain transaction isolation levels and how MVCC works in PostgreSQL.", ["isolation", "mvcc", "snapshot", "read committed", "serializable"])],
    },
    "SQL": {
        "easy": [("What is the difference between INNER JOIN and LEFT JOIN?", ["join", "match", "null", "rows"])],
        "medium": [("When would you use GROUP BY with HAVING, and how is it different from WHERE?", ["group", "aggregate", "filter", "having", "where"])],
        "hard": [("How would you debug and optimise a slow SQL query?", ["explain", "index", "plan", "scan", "join"])],
    },
    "Docker": {
        "easy": [("What is the difference between a Docker image and a container?", ["image", "container", "layer", "run"])],
        "medium": [("How do you keep Docker images small and builds fast?", ["multi-stage", "cache", "layer", "alpine", "dockerignore"])],
        "hard": [("How would you run and isolate untrusted code safely in containers?", ["sandbox", "cgroup", "namespace", "limit", "network", "seccomp"])],
    },
    "JavaScript": {
        "easy": [("What is the difference between let, const and var?", ["scope", "hoist", "block", "reassign"])],
        "medium": [("Explain closures and the event loop in JavaScript.", ["closure", "scope", "event loop", "callback", "promise", "async"])],
        "hard": [("How do promises, microtasks and macrotasks interact in the event loop?", ["microtask", "macrotask", "promise", "queue", "settimeout"])],
    },
    "AWS": {
        "easy": [("What are EC2 and S3 used for?", ["compute", "storage", "instance", "bucket"])],
        "medium": [("How would you design a highly available web application on AWS?", ["load balancer", "availability", "auto scaling", "multi-az", "rds"])],
        "hard": [("How would you secure and cost-optimise a multi-account AWS setup?", ["iam", "least privilege", "vpc", "cost", "organizations"])],
    },
}

GENERIC = {
    "easy": "Explain what {s} is and describe where you have used it.",
    "medium": "Describe a challenging problem you solved using {s} and the approach you took.",
    "hard": "How would you design, scale and troubleshoot a production system that relies heavily on {s}? Discuss trade-offs.",
}

HR_QUESTIONS = [
    "Tell me about yourself and why you are interested in this role.",
    "Describe a time you handled a disagreement with a teammate.",
    "Tell me about a project you are most proud of and your contribution.",
    "How do you handle tight deadlines and changing priorities?",
    "Where do you see yourself in the next three years?",
]

HEDGES = ["maybe", "i guess", "not sure", "i think", "probably", "kind of", "sort of", "um", "uh", "i don't know"]
REASONING = ["because", "therefore", "however", "for example", "for instance", "trade-off", "tradeoff",
             "first", "then", "if ", "so that", "which means", "as a result", "instead"]
STOP = set("the a an and or of to in on for with is are was were be been how what why when do does did you your "
           "can could would should explain describe tell about between using use that this it as at by from".split())


def _tokens(text):
    return [w for w in re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", (text or "").lower()) if w not in STOP]


def _clamp(v):
    return round(max(0.0, min(100.0, float(v))), 1)


def _bank_question(skill, difficulty):
    entry = BANK.get(skill, {}).get(difficulty)
    if entry:
        q, kws = random.choice(entry)
        return {"text": q, "topic": skill, "difficulty": difficulty, "expected_points": kws}
    return {"text": GENERIC[difficulty].format(s=skill), "topic": skill, "difficulty": difficulty, "expected_points": []}


def _topics(job, resume):
    """Prioritise skills required by the job that the candidate also claims, then the rest."""
    req = canonicalize_list(job.get("required_skills"))
    have = {s.lower() for s in canonicalize_list(resume.get("skills"))}
    ordered = [s for s in req if s.lower() in have] + [s for s in req if s.lower() not in have]
    ordered += [s for s in canonicalize_list(resume.get("skills")) if s not in ordered]
    if not ordered:
        ordered = extract_skills(job.get("description", "")) or ["Python"]
    return ordered


def generate_questions(job: dict, resume: dict, round_type: str = "technical", difficulty: str = "medium",
                       count: int = 5, exclude=None) -> list:
    exclude = {e.lower() for e in (exclude or [])}
    if llm.llm_available():
        data = llm.llm_json(
            "You are an expert technical interviewer. Return {\"questions\": [{\"text\": str, \"topic\": str, "
            "\"difficulty\": \"easy|medium|hard\", \"expected_points\": [str]}]}.",
            f"Job: {job}\nCandidate skills/experience: {resume}\nRound: {round_type}\nTarget difficulty: {difficulty}\n"
            f"Generate {count} distinct questions tailored to the job and candidate. Avoid: {list(exclude)}",
        )
        qs = (data or {}).get("questions") if isinstance(data, dict) else None
        if qs:
            return [{"text": q.get("text", ""), "topic": q.get("topic", ""),
                     "difficulty": q.get("difficulty", difficulty),
                     "expected_points": q.get("expected_points", [])} for q in qs[:count] if q.get("text")]

    if round_type in ("hr", "final"):
        pool = [q for q in HR_QUESTIONS if q.lower() not in exclude]
        return [{"text": q, "topic": "behavioral", "difficulty": "easy", "expected_points": []} for q in pool[:count]]

    out, topics = [], _topics(job, resume)
    level = difficulty if difficulty in DIFFICULTIES else "medium"
    i = 0
    while len(out) < count and i < count * 4:
        skill = topics[i % len(topics)]
        lvl = level if i < len(topics) else DIFFICULTIES[min(2, DIFFICULTIES.index(level) + i // len(topics))]
        q = _bank_question(skill, lvl)
        if q["text"].lower() not in exclude and q["text"] not in [o["text"] for o in out]:
            out.append(q)
        i += 1
    return out


def analyze_answer(question: str, answer: str, expected_points=None, job: dict = None) -> dict:
    """Score an answer on 0-100 criteria and produce strengths / improvements."""
    if llm.llm_available() and (answer or "").strip():
        data = llm.llm_json(
            "You evaluate interview answers fairly. Return {\"technical_score\": 0-100, \"communication_score\": 0-100, "
            "\"problem_solving_score\": 0-100, \"relevance_score\": 0-100, \"confidence_score\": 0-100, "
            "\"strengths\": [str], \"improvements\": [str]}.",
            f"Job context: {job}\nQuestion: {question}\nExpected points: {expected_points}\nAnswer: {answer}",
        )
        if isinstance(data, dict) and "technical_score" in data:
            s = {k: _clamp(data.get(k, 0)) for k in ("technical_score", "communication_score",
                                                      "problem_solving_score", "relevance_score", "confidence_score")}
            return _finalize(s, data.get("strengths", []), data.get("improvements", []), "llm")
    return _heuristic(question, answer, expected_points or [])


def _heuristic(question, answer, expected):
    answer = (answer or "").strip()
    low = answer.lower()
    words = re.findall(r"\w+", low)
    n = len(words)
    if n == 0:
        zero = {k: 0.0 for k in ("technical_score", "communication_score", "problem_solving_score",
                                 "relevance_score", "confidence_score")}
        return _finalize(zero, [], ["No answer was provided."], "heuristic")

    length_factor = min(1.0, n / 80)
    coverage = (sum(1 for kw in expected if kw.lower() in low) / len(expected)) if expected else None
    q_tokens = set(_tokens(question))
    overlap = len(q_tokens & set(_tokens(answer))) / max(1, min(len(q_tokens), 6))
    relevance = _clamp(35 + 65 * min(1.0, overlap)) if n >= 5 else 20.0

    tech_terms = len(extract_skills(answer))
    if coverage is not None:
        technical = _clamp(100 * (0.7 * coverage + 0.3 * length_factor))
    else:
        technical = _clamp(30 + 40 * length_factor + 10 * min(3, tech_terms))

    sentences = [s for s in re.split(r"[.!?]+", answer) if s.strip()]
    avg_len = n / max(1, len(sentences))
    structure = 1.0 if 8 <= avg_len <= 25 else 0.7
    communication = _clamp(40 + 35 * length_factor * structure + 25 * structure)

    hedges = sum(low.count(h) for h in HEDGES)
    confidence = _clamp(100 - 8 * hedges - (20 if n < 10 else 0))

    reasoning = sum(1 for r in REASONING if r in low)
    problem_solving = _clamp(35 + 10 * min(5, reasoning) + (15 * coverage if coverage is not None else 5 * min(3, tech_terms)))

    s = {"technical_score": technical, "communication_score": communication,
         "problem_solving_score": problem_solving, "relevance_score": relevance, "confidence_score": confidence}

    strengths, improvements = [], []
    if coverage is not None and coverage >= 0.6:
        strengths.append("Covered most of the key technical concepts.")
    if reasoning >= 3:
        strengths.append("Explained reasoning with examples or trade-offs.")
    if relevance >= 75:
        strengths.append("Answer was relevant and on topic.")
    if coverage is not None and coverage < 0.4:
        missing = [kw for kw in expected if kw.lower() not in low][:4]
        improvements.append("Missing key concepts: " + ", ".join(missing) + ".")
    if n < 40:
        improvements.append("Answer was brief; add detail and a concrete example.")
    if hedges >= 3:
        improvements.append("Several hesitant phrases; state points more directly.")
    return _finalize(s, strengths, improvements, "heuristic")


def _finalize(scores, strengths, improvements, provider):
    overall = _clamp(0.35 * scores["technical_score"] + 0.20 * scores["communication_score"]
                     + 0.20 * scores["problem_solving_score"] + 0.15 * scores["relevance_score"]
                     + 0.10 * scores["confidence_score"])
    level = "strong" if overall >= 75 else "ok" if overall >= 50 else "weak"
    return {**scores, "overall_score": overall, "level": level, "strengths": strengths,
            "improvements": improvements, "provider": provider,
            "disclaimer": "Automated scores are decision-support signals and must be reviewed by a human."}


def next_question(job: dict, resume: dict, history: list, round_type: str = "technical") -> dict:
    """
    Adaptive follow-up. `history` = [{text, topic, difficulty, overall_score}, ...] in asked order.
    Strong answer -> harder question on a new topic; weak answer -> easier follow-up on the same topic.
    """
    asked = [h["text"] for h in history]
    if not history:
        return generate_questions(job, resume, round_type, "easy", 1)[0]

    last = history[-1]
    score = float(last.get("overall_score") or 0)
    idx = DIFFICULTIES.index(last["difficulty"]) if last.get("difficulty") in DIFFICULTIES else 1
    if score >= 75:
        idx = min(2, idx + 1)
    elif score < 50:
        idx = max(0, idx - 1)
    difficulty = DIFFICULTIES[idx]

    if round_type in ("hr", "final"):
        qs = generate_questions(job, resume, round_type, "easy", 5, exclude=asked)
        return qs[0] if qs else {"text": "Do you have any questions for us?", "topic": "behavioral",
                                 "difficulty": "easy", "expected_points": []}

    if llm.llm_available():
        data = llm.llm_json(
            "You are an adaptive technical interviewer. Return {\"text\": str, \"topic\": str, \"difficulty\": str, "
            "\"expected_points\": [str]}.",
            f"Job: {job}\nCandidate: {resume}\nHistory (question, difficulty, score): "
            f"{[(h['text'], h.get('difficulty'), h.get('overall_score')) for h in history]}\n"
            f"Ask ONE new question at '{difficulty}' difficulty. "
            + ("Follow up on the same topic, simpler." if score < 50 else "Move to a related or new topic."),
        )
        if isinstance(data, dict) and data.get("text") and data["text"] not in asked:
            data.setdefault("expected_points", [])
            data["difficulty"] = difficulty
            return data

    topics = _topics(job, resume)
    last_topic = last.get("topic")
    if score < 50 and last_topic in topics:
        order = [last_topic] + [t for t in topics if t != last_topic]
    else:
        order = [t for t in topics if t != last_topic] + ([last_topic] if last_topic in topics else [])
    for skill in order or topics:
        for lvl in [difficulty] + [d for d in DIFFICULTIES if d != difficulty]:
            q = _bank_question(skill, lvl)
            if q["text"] not in asked:
                return q
    return {"text": "Describe the most technically challenging problem you have solved recently.",
            "topic": "general", "difficulty": difficulty, "expected_points": []}
