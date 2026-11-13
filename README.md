# AI-Powered Recruitment & Intelligent Interview Platform — Backend

Django 5 + Django REST Framework, JWT auth, custom user model, 4 apps:

```
server/
├── manage.py
├── config/          settings, root urls, wsgi/asgi
├── accounts/        custom User (email login + roles), Company, CandidateProfile, AuditLog, auth, staff & admin APIs
├── recruitment/     jobs, resumes, applications (AI screening), coding assessments + code runner,
│                    scorecards/comparison, hiring decisions, offers, notifications, analytics
├── interviews/      interview scheduling, AI questions (adaptive), answer analysis, feedback, integrity events
└── ai_engine/       resume parser, skill taxonomy, job matcher, interview AI (LLM optional), AI run logs + AI APIs
```

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # SQLite by default; set DB_ENGINE=postgres for PostgreSQL
python manage.py makemigrations accounts recruitment interviews ai_engine
python manage.py migrate
python manage.py seed_demo      # optional demo data (password: Demo@12345)
python manage.py test           # smoke test of the full hiring flow
python manage.py runserver
```

* Swagger UI: `/api/docs/`   OpenAPI schema: `/api/schema/`   Admin: `/admin/`
* Run `makemigrations` with the app names (as above) the first time: the custom user model must be migrated first.
* Auth header: `Authorization: Bearer <access>`

## Roles (`accounts.User.role`)
`super_admin`, `company_admin`, `hr`, `interviewer`, `candidate`. Every queryset is scoped by role/company
(candidates see only their own data, interviewers only their assigned interviews, company staff only their company).

## REST API (all under `/api/`)

### accounts
| Method & path | Who | Purpose |
|---|---|---|
| POST `auth/register/company/` | public | Register company + first Company Admin |
| POST `auth/register/candidate/` | public | Candidate sign-up |
| POST `auth/login/` · `auth/refresh/` · `auth/logout/` | public/any | JWT (email + password) |
| GET/PATCH `auth/me/` · POST `auth/change-password/` | any | Own account |
| GET/PATCH `candidate-profile/` | candidate | Profile (education, skills, links…) |
| `companies/` (+ `companies/me/`) | members / admin | Company profile |
| `staff/` | company admin | Create/manage HR & interviewer accounts (soft delete) |
| `admin/users/` (+ `activate/`, `deactivate/`) | super admin | Manage all users |
| GET `audit-logs/` | admin | Audit trail |

### recruitment
| Path | Purpose |
|---|---|
| `jobs/` (+ `publish/`, `close/`, `applications/`) | Job CRUD with hiring stages; candidates browse open jobs |
| `resumes/` (+ `make_primary/`) | Upload PDF/DOCX/TXT → parsed + skills extracted (candidate) |
| `applications/` | Candidate applies → **AI screening runs automatically** |
| `applications/{id}/screen/ · shortlist/ · set-status/ · history/ · resume/ · withdraw/` | Pipeline actions |
| `applications/{id}/scorecard/` (GET recompute, PATCH remarks/recommendation) | Candidate scorecard |
| POST `applications/compare/` `{application_ids:[..]}` | Candidate comparison |
| `candidates/` | HR view of candidates who applied |
| `coding-problems/` | Problems + test cases (hidden cases supported) |
| `assessments/` (+ `assign/`) | Assessments, assign to applications |
| `assessment-attempts/` (+ `start/ problems/ submit-code/ finish/ submissions/`) | Candidate takes test; code is executed against test cases |
| `hiring-decisions/` | Selected / Rejected / Hold (updates pipeline status) |
| `offers/` (+ `send/ withdraw/ respond/`) | Offer lifecycle; accepting marks candidate **hired** |
| `notifications/` (+ `mark-read/ mark-all-read/ unread-count/`) | In-app notifications |
| GET `analytics/dashboard/` | Totals, hiring funnel, time-to-hire, per-job/department stats |

### interviews
| Path | Purpose |
|---|---|
| `interviews/` | Schedule rounds (human or AI-conducted) |
| `interviews/{id}/confirm/ · reschedule/ · cancel/ · start/ · complete/` | Lifecycle |
| `interviews/{id}/generate-questions/` | AI questions from job + resume |
| `interviews/{id}/next-question/` · `answer/` | **Adaptive** interview: harder after strong answers, easier after weak ones |
| `interviews/{id}/ai-summary/` · `feedback/` | AI analysis summary · interviewer ratings & recommendation |
| `integrity-events/` (+ `review/`, `summary/?interview=`) | Face/voice/tab anomaly signals → human review |

### ai_engine (`/api/ai/`)
`status/`, `resume/parse/`, `match/`, `questions/generate/`, `answers/analyze/`, `logs/`

## AI behaviour
* Works offline with deterministic heuristics (skill taxonomy, weighted matcher, keyword/structure scoring).
* Set `ANTHROPIC_API_KEY` to let an LLM refine resume parsing, question generation and answer analysis;
  any failure silently falls back to the heuristics.
* All AI scores are labelled decision-support signals; integrity events require human review.

## Security notes / production checklist
* **Code runner is not a sandbox** (`recruitment/code_runner.py`). Run it in isolated, network-less containers via a
  Celery worker and set `CODE_EXECUTION_ENABLED=False` on the web tier.
* Set `DJANGO_DEBUG=False`, a real `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, HTTPS and `CORS_ALLOWED_ORIGINS`.
* Put uploaded media on object storage (S3/GCS); add virus scanning for resumes.
* Not included yet (natural next steps): Celery/Redis tasks, Django Channels/WebRTC signalling, the computer-vision
  worker that produces `integrity-events`, email delivery for notifications.
