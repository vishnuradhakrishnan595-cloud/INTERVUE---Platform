from django.urls import path

from . import views

urlpatterns = [
    # JOBS
    path("jobs/", views.JobListCreateView.as_view(), name="job-list-create"),
    path("jobs/<int:pk>/", views.JobDetailView.as_view(), name="job-detail"),
    path("jobs/<int:pk>/publish/", views.JobPublishView.as_view(), name="job-publish"),
    path("jobs/<int:pk>/close/", views.JobCloseView.as_view(), name="job-close"),
    path(
        "jobs/<int:pk>/applications/",
        views.JobApplicationsView.as_view(),
        name="job-applications",
    ),

    # SAVED JOBS
    path(
        "saved-jobs/",
        views.SavedJobListCreateView.as_view(),
        name="saved-job-list-create",
    ),
    path(
        "saved-jobs/<int:pk>/",
        views.SavedJobDetailView.as_view(),
        name="saved-job-detail",
    ),

    # RESUMES
    path("resumes/", views.ResumeListCreateView.as_view(), name="resume-list-create"),
    path("resumes/<int:pk>/", views.ResumeDetailView.as_view(), name="resume-detail"),
    path(
        "resumes/<int:pk>/make-primary/",
        views.ResumeMakePrimaryView.as_view(),
        name="resume-make-primary",
    ),

    # APPLICATIONS
    path(
        "applications/",
        views.ApplicationListCreateView.as_view(),
        name="application-list-create",
    ),
    # Keep the fixed path before applications/<int:pk>/.
    path(
        "applications/compare/",
        views.ApplicationCompareView.as_view(),
        name="application-compare",
    ),
    path(
        "applications/<int:pk>/",
        views.ApplicationDetailView.as_view(),
        name="application-detail",
    ),
    path(
        "applications/<int:pk>/withdraw/",
        views.ApplicationWithdrawView.as_view(),
        name="application-withdraw",
    ),
    path(
        "applications/<int:pk>/screen/",
        views.ApplicationScreenView.as_view(),
        name="application-screen",
    ),
    path(
        "applications/<int:pk>/shortlist/",
        views.ApplicationShortlistView.as_view(),
        name="application-shortlist",
    ),
    path(
        "applications/<int:pk>/set-status/",
        views.ApplicationSetStatusView.as_view(),
        name="application-set-status",
    ),
    path(
        "applications/<int:pk>/resume/",
        views.ApplicationResumeView.as_view(),
        name="application-resume",
    ),
    path(
        "applications/<int:pk>/history/",
        views.ApplicationHistoryView.as_view(),
        name="application-history",
    ),
    path(
        "applications/<int:pk>/scorecard/",
        views.ApplicationScorecardView.as_view(),
        name="application-scorecard",
    ),

    # CANDIDATES
    path("candidates/", views.CandidateListView.as_view(), name="candidate-list"),
    path(
        "candidates/<int:pk>/",
        views.CandidateDetailView.as_view(),
        name="candidate-detail",
    ),

    # CODING PROBLEMS
    path(
        "coding-problems/",
        views.CodingProblemListCreateView.as_view(),
        name="coding-problem-list-create",
    ),
    path(
        "coding-problems/<int:pk>/",
        views.CodingProblemDetailView.as_view(),
        name="coding-problem-detail",
    ),

    # ASSESSMENTS
    path(
        "assessments/",
        views.AssessmentListCreateView.as_view(),
        name="assessment-list-create",
    ),
    path(
        "assessments/<int:pk>/",
        views.AssessmentDetailView.as_view(),
        name="assessment-detail",
    ),
    path(
        "assessments/<int:pk>/assign/",
        views.AssessmentAssignView.as_view(),
        name="assessment-assign",
    ),

    # ASSESSMENT ATTEMPTS
    path(
        "assessment-attempts/",
        views.AttemptListView.as_view(),
        name="assessment-attempt-list",
    ),
    path(
        "assessment-attempts/<int:pk>/",
        views.AttemptDetailView.as_view(),
        name="assessment-attempt-detail",
    ),
    path(
        "assessment-attempts/<int:pk>/start/",
        views.AttemptStartView.as_view(),
        name="assessment-attempt-start",
    ),
    path(
        "assessment-attempts/<int:pk>/problems/",
        views.AttemptProblemsView.as_view(),
        name="assessment-attempt-problems",
    ),
    path(
        "assessment-attempts/<int:pk>/submit-code/",
        views.AttemptSubmitCodeView.as_view(),
        name="assessment-attempt-submit-code",
    ),
    path(
        "assessment-attempts/<int:pk>/finish/",
        views.AttemptFinishView.as_view(),
        name="assessment-attempt-finish",
    ),
    path(
        "assessment-attempts/<int:pk>/submissions/",
        views.AttemptSubmissionsView.as_view(),
        name="assessment-attempt-submissions",
    ),

    # HIRING DECISIONS
    path(
        "hiring-decisions/",
        views.HiringDecisionListCreateView.as_view(),
        name="hiring-decision-list-create",
    ),
    path(
        "hiring-decisions/<int:pk>/",
        views.HiringDecisionDetailView.as_view(),
        name="hiring-decision-detail",
    ),

    # OFFERS
    path("offers/", views.OfferListCreateView.as_view(), name="offer-list-create"),
    path("offers/<int:pk>/", views.OfferDetailView.as_view(), name="offer-detail"),
    path("offers/<int:pk>/send/", views.OfferSendView.as_view(), name="offer-send"),
    path(
        "offers/<int:pk>/withdraw/",
        views.OfferWithdrawView.as_view(),
        name="offer-withdraw",
    ),
    path(
        "offers/<int:pk>/respond/",
        views.OfferRespondView.as_view(),
        name="offer-respond",
    ),

    # NOTIFICATIONS
    path(
        "notifications/",
        views.NotificationListView.as_view(),
        name="notification-list",
    ),
    path(
        "notifications/mark-all-read/",
        views.NotificationMarkAllReadView.as_view(),
        name="notification-mark-all-read",
    ),
    path(
        "notifications/unread-count/",
        views.NotificationUnreadCountView.as_view(),
        name="notification-unread-count",
    ),
    path(
        "notifications/<int:pk>/",
        views.NotificationDetailView.as_view(),
        name="notification-detail",
    ),
    path(
        "notifications/<int:pk>/mark-read/",
        views.NotificationMarkReadView.as_view(),
        name="notification-mark-read",
    ),

    # ANALYTICS
    path(
        "analytics/dashboard/",
        views.DashboardView.as_view(),
        name="analytics-dashboard",
    ),
]