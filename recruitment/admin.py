from django.contrib import admin

from . import models

for m in (models.Job, models.JobStage, models.Resume, models.Application, models.ApplicationStatusHistory,
          models.CodingProblem, models.ProblemTestCase, models.Assessment, models.AssessmentAttempt,
          models.Submission, models.CandidateScore, models.HiringDecision, models.Offer, models.Notification):
    admin.site.register(m)
