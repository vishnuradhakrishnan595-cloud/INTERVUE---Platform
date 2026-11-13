from django.urls import path
from . import views

urlpatterns = [
    # Interviews
    path(
        "interviews/",
        views.InterviewListCreateView.as_view(),
        name="interview-list-create",
    ),

    
    path(
        "interviews/<int:pk>/",
        views.InterviewDetailView.as_view(),
        name="interview-detail",
    ),
    path(
        "interviews/<int:pk>/confirm/",
        views.InterviewConfirmView.as_view(),
        name="interview-confirm",
    ),
    path(
        "interviews/<int:pk>/reschedule/",
        views.InterviewRescheduleView.as_view(),
        name="interview-reschedule",
    ),
    path(
        "interviews/<int:pk>/cancel/",
        views.InterviewCancelView.as_view(),
        name="interview-cancel",
    ),
    path(
        "interviews/<int:pk>/start/",
        views.InterviewStartView.as_view(),
        name="interview-start",
    ),
    path(
        "interviews/<int:pk>/complete/",
        views.InterviewCompleteView.as_view(),
        name="interview-complete",
    ),
    path(
        "interviews/<int:pk>/questions/",
        views.InterviewQuestionsView.as_view(),
        name="interview-questions",
    ),
    path(
        "interviews/<int:pk>/generate-questions/",
        views.InterviewGenerateQuestionsView.as_view(),
        name="interview-generate-questions",
    ),
    path(
        "interviews/<int:pk>/next-question/",
        views.InterviewNextQuestionView.as_view(),
        name="interview-next-question",
    ),
    path(
        "interviews/<int:pk>/answer/",
        views.InterviewAnswerView.as_view(),
        name="interview-answer",
    ),
    path(
        "interviews/<int:pk>/ai-summary/",
        views.InterviewAISummaryView.as_view(),
        name="interview-ai-summary",
    ),
    path(
        "interviews/<int:pk>/feedback/",
        views.InterviewFeedbackView.as_view(),
        name="interview-feedback",
    ),

    # Integrity events
    path(
        "integrity-events/",
        views.IntegrityEventListCreateView.as_view(),
        name="integrity-event-list-create",
    ),
    path(
        "integrity-events/summary/",
        views.IntegrityEventSummaryView.as_view(),
        name="integrity-event-summary",
    ),
    path(
        "integrity-events/<int:pk>/",
        views.IntegrityEventDetailView.as_view(),
        name="integrity-event-detail",
    ),
    path(
        "integrity-events/<int:pk>/review/",
        views.IntegrityEventReviewView.as_view(),
        name="integrity-event-review",
    ),

    # WebRTC
    path("webrtc/config/", views.WebRTCConfigView.as_view(), name="webrtc-config"),
    path(
        "interviews/<int:interview_id>/webrtc-config/",
        views.WebRTCConfigView.as_view(),
        name="interview-webrtc-config",
    ),
]
