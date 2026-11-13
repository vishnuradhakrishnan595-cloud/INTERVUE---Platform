
from django.urls import path

from . import views


urlpatterns = [

    # ============================================================
    # AI STATUS
    # GET /api/ai/status/
    # ============================================================

    path(
        "status/",
        views.StatusView.as_view(),
        name="ai-status",
    ),

    # ============================================================
    # RESUME PARSING
    # POST /api/ai/resume/parse/
    # ============================================================

    path(
        "resume/parse/",
        views.ParseResumeView.as_view(),
        name="ai-resume-parse",
    ),

    # ============================================================
    # JOB MATCHING
    # POST /api/ai/match/
    # ============================================================

    path(
        "match/",
        views.MatchView.as_view(),
        name="ai-match",
    ),

    # ============================================================
    # INTERVIEW QUESTION GENERATION
    # POST /api/ai/questions/generate/
    # ============================================================

    path(
        "questions/generate/",
        views.GenerateQuestionsView.as_view(),
        name="ai-generate-questions",
    ),

    # ============================================================
    # ANSWER ANALYSIS
    # POST /api/ai/answers/analyze/
    # ============================================================

    path(
        "answers/analyze/",
        views.AnalyzeAnswerView.as_view(),
        name="ai-analyze-answer",
    ),

    # ============================================================
    # AI RUN LOGS
    # GET /api/ai/logs/
    # ============================================================

    path(
        "logs/",
        views.AIRunLogListView.as_view(),
        name="ai-log-list",
    ),

    # ============================================================
    # AI RUN LOG DETAIL
    # GET /api/ai/logs/<id>/
    # ============================================================

    path(
        "logs/<int:pk>/",
        views.AIRunLogDetailView.as_view(),
        name="ai-log-detail",
    ),
]
