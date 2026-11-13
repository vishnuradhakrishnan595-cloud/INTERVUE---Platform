"""Skill taxonomy + extraction. Canonical name -> list of aliases (all lowercase)."""
import re

SKILLS = {
    "Python": ["python", "python3"],
    "Django": ["django"],
    "Django REST Framework": ["drf", "django rest framework", "django-rest-framework"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "REST API": ["rest api", "rest apis", "restful", "restful api", "restful apis"],
    "GraphQL": ["graphql"],
    "Celery": ["celery"],
    "React": ["react", "reactjs", "react.js"],
    "Redux": ["redux"],
    "Next.js": ["next.js", "nextjs"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
    "Angular": ["angular", "angularjs"],
    "JavaScript": ["javascript", "js", "ecmascript"],
    "TypeScript": ["typescript"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "Express": ["express", "express.js", "expressjs"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Java": ["java"],
    "Spring Boot": ["spring boot", "springboot"],
    "C++": ["c++"],
    "C#": ["c#"],
    ".NET": [".net", "dotnet", "asp.net"],
    "Go": ["golang"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql"],
    "SQL": ["sql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq"],
    "Docker": ["docker", "dockerfile", "docker-compose"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "Nginx": ["nginx"],
    "Linux": ["linux", "ubuntu"],
    "Git": ["git", "github", "gitlab"],
    "CI/CD": ["ci/cd", "cicd", "jenkins", "github actions"],
    "WebSockets": ["websocket", "websockets", "django channels"],
    "WebRTC": ["webrtc"],
    "JWT": ["jwt"],
    "OAuth": ["oauth", "oauth2"],
    "Microservices": ["microservices", "microservice"],
    "System Design": ["system design"],
    "Data Structures": ["data structures", "dsa", "algorithms"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "OpenCV": ["opencv"],
    "MediaPipe": ["mediapipe"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "Pytest": ["pytest"],
    "Unit Testing": ["unit testing", "unit tests"],
    "Agile": ["agile", "scrum"],
}

_ALIAS_TO_CANON = {}
_PATTERNS = []
for canon, aliases in SKILLS.items():
    for alias in set(aliases + [canon.lower()]):
        _ALIAS_TO_CANON[alias] = canon
        _PATTERNS.append((canon, re.compile(r"(?<![A-Za-z0-9+#.])" + re.escape(alias) + r"(?![A-Za-z0-9+#])", re.I)))


def canonicalize(name: str) -> str:
    key = (name or "").strip().lower()
    return _ALIAS_TO_CANON.get(key) or (name or "").strip()


def canonicalize_list(names):
    seen, out = set(), []
    for n in names or []:
        c = canonicalize(str(n))
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def extract_skills(text: str):
    """Return canonical skills found in free text, in the order of the taxonomy."""
    found = []
    for canon, pat in _PATTERNS:
        if canon not in found and pat.search(text or ""):
            found.append(canon)
    return found
