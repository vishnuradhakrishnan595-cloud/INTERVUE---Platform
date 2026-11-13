"""Business logic shared by views: notifications, AI screening, status changes, scorecards."""
from django.conf import settings
from django.db.models import Avg

from accounts.models import CandidateProfile
from ai_engine.services import matcher

from .models import Application, ApplicationStatusHistory, CandidateScore, Notification

STATUS_MESSAGES = {
    "screening": "Your application is being screened.",
    "shortlisted": "Congratulations! You have been shortlisted.",
    "assessment": "A coding assessment has been assigned to you.",
    "interview": "You have moved to the interview stage.",
    "final_review": "Your application is in final review.",
    "selected": "Great news! You have been selected.",
    "rejected": "Thank you for applying. Unfortunately we will not be moving forward.",
    "withdrawn": "Your application has been withdrawn.",
    "hired": "Welcome aboard! Your hiring is confirmed.",
}


def notify(user, title, message="", ntype="info", link=""):
    if user is None:
        return None
    return Notification.objects.create(user=user, title=title, message=message, type=ntype, link=link)


def notify_company_staff(company, roles, title, message="", ntype="info", link=""):
    from accounts.models import User
    for u in User.objects.filter(company=company, role__in=roles, is_active=True):
        notify(u, title, message, ntype, link)


def change_status(application, new_status, by=None, note="", notify_candidate=True):
    old = application.status
    if old == new_status:
        return application
    application.status = new_status
    application.save(update_fields=["status", "updated_at"])
    ApplicationStatusHistory.objects.create(application=application, from_status=old, to_status=new_status,
                                            changed_by=by, note=note)
    if notify_candidate and new_status in STATUS_MESSAGES:
        notify(application.candidate, f"Application update: {application.job.title}",
               STATUS_MESSAGES[new_status], "application", f"/applications/{application.pk}")
    return application


def build_job_context(job):
    return {
        "title": job.title, "required_skills": job.required_skills, "preferred_skills": job.preferred_skills,
        "experience_min": job.experience_min, "education": job.education, "description": job.description[:2000],
    }


def build_candidate_context(application):
    """Prefer the parsed resume; fall back to the candidate profile."""
    resume = application.resume
    profile = CandidateProfile.objects.filter(user=application.candidate).first()
    parsed = (resume.parsed_data if resume else {}) or {}
    skills = list(resume.skills) if resume and resume.skills else list(getattr(profile, "skills", []) or [])
    years = parsed.get("experience_years") or getattr(profile, "experience_years", 0) or 0
    education = parsed.get("education") or getattr(profile, "education", []) or []
    return {"skills": skills, "experience_years": years, "education": education}


def screen_application(application, by=None):
    """AI resume screening: compute job-match scores and store them on the application."""
    result = matcher.compute_match(build_job_context(application.job), build_candidate_context(application))
    application.skill_match = result["skill_match"]
    application.experience_match = result["experience_match"]
    application.education_match = result["education_match"]
    application.overall_match = result["overall_match"]
    application.matched_skills = result["matched_skills"]
    application.missing_skills = result["missing_skills"]
    application.ai_summary = result["summary"]
    application.save()
    if application.status == Application.Status.APPLIED:
        change_status(application, Application.Status.SCREENING, by=by, note="AI screening completed")
    return application


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def recompute_scorecard(application):
    """Aggregate resume, coding, AI-interview and interviewer-feedback signals into one scorecard."""
    from interviews.models import InterviewAnswer, InterviewFeedback  # local import: avoids circular deps

    card, _ = CandidateScore.objects.get_or_create(application=application)

    attempt = application.assessment_attempts.filter(status="submitted").exclude(score=None).order_by("-submitted_at").first()
    coding = attempt.score if attempt else None

    ai = InterviewAnswer.objects.filter(question__interview__application=application).aggregate(
        o=Avg("overall_score"), c=Avg("communication_score"), p=Avg("problem_solving_score"))
    fb = InterviewFeedback.objects.filter(interview__application=application).aggregate(
        t=Avg("technical_rating"), c=Avg("communication_rating"), p=Avg("problem_solving_rating"))
    fb_t, fb_c, fb_p = (v * 20 if v is not None else None for v in (fb["t"], fb["c"], fb["p"]))

    interview = _mean([ai["o"], _mean([fb_t, fb_c, fb_p])])
    card.resume_score = application.overall_match
    card.coding_score = coding
    card.interview_score = interview
    card.communication_score = _mean([ai["c"], fb_c])
    card.problem_solving_score = _mean([ai["p"], fb_p])

    weights, parts = settings.SCORE_WEIGHTS, {"resume": card.resume_score, "coding": coding, "interview": interview}
    avail = {k: v for k, v in parts.items() if v is not None}
    wsum = sum(weights[k] for k in avail) or 1
    card.overall_score = round(sum(v * weights[k] for k, v in avail.items()) / wsum, 1)
    o = card.overall_score
    card.suggested_recommendation = ("strong_hire" if o >= 85 else "hire" if o >= 70 else "hold" if o >= 55 else "no_hire")
    card.save()
    return card
