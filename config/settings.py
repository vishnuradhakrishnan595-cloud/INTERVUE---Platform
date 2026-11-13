import os
from datetime import timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")]


INSTALLED_APPS = [
    # ASGI server (WebSocket support for runserver) - must be first
    "daphne",

    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "rest_framework",
    "channels",

    # Your apps
    "accounts",
    
    "recruitment",
    
    "interviews",
    "ai_engine",
]

# Django Channels Configuration

ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------- Database
if os.getenv("DB_ENGINE", "").lower() in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "recruitment"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }

# ---------------------------------------------------------------- Auth
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/min",
        "user": "600/min",
        "auth": "20/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AI-Powered Recruitment & Intelligent Interview Platform API",
    "DESCRIPTION": "REST API for hiring workflow, coding assessments, AI interviews and analytics.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------- CORS
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

# ---------------------------------------------------------------- WebSocket (Channels)
# Set REDIS_URL (e.g. redis://127.0.0.1:6379/0) to use Redis so that WebSocket
# messages work across multiple server processes. Without it, the in-memory layer
# above is used (fine for development / a single process).
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        },
    }

# Origins allowed to open a WebSocket (checked in asgi.py). "*" allows all (dev only).
WS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("WS_ALLOWED_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS)).split(",")
    if o.strip()
]
# Require a valid JWT (?token=<access token>) to join the interview signalling socket.
WS_REQUIRE_AUTH = os.getenv("WS_REQUIRE_AUTH", "False") == "True"

# ---------------------------------------------------------------- WebRTC
# ICE servers handed to the browser's RTCPeerConnection (sent on WebSocket connect
# and from GET /api/webrtc/config/). Add a TURN server for users behind strict NATs.
WEBRTC_STUN_URLS = [
    u.strip()
    for u in os.getenv(
        "WEBRTC_STUN_URLS",
        "stun:stun.l.google.com:19302,stun:stun1.l.google.com:19302",
    ).split(",")
    if u.strip()
]
WEBRTC_TURN_URLS = [u.strip() for u in os.getenv("WEBRTC_TURN_URLS", "").split(",") if u.strip()]
WEBRTC_TURN_USERNAME = os.getenv("WEBRTC_TURN_USERNAME", "")
WEBRTC_TURN_CREDENTIAL = os.getenv("WEBRTC_TURN_CREDENTIAL", "")

WEBRTC_ICE_SERVERS = [{"urls": WEBRTC_STUN_URLS}] if WEBRTC_STUN_URLS else []
if WEBRTC_TURN_URLS:
    WEBRTC_ICE_SERVERS.append({
        "urls": WEBRTC_TURN_URLS,
        "username": WEBRTC_TURN_USERNAME,
        "credential": WEBRTC_TURN_CREDENTIAL,
    })

# ---------------------------------------------------------------- Platform settings
RESUME_MAX_MB = 5
RESUME_ALLOWED_EXTENSIONS = ["pdf", "docx", "txt"]

# weights used when building the candidate scorecard (renormalised over available parts)
SCORE_WEIGHTS = {"resume": 0.20, "coding": 0.30, "interview": 0.50}

# AI provider (optional – heuristic fallbacks are used when no key is configured)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# Local subprocess code runner. NOT a real sandbox: use isolated Docker workers in production.
CODE_EXECUTION_ENABLED = os.getenv("CODE_EXECUTION_ENABLED", "True") == "True"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True") == "True"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
