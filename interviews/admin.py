from django.contrib import admin

from . import models

for m in (models.Interview, models.InterviewQuestion, models.InterviewAnswer, models.InterviewFeedback,
          models.IntegrityEvent):
    admin.site.register(m)
