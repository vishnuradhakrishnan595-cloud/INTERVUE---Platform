"""python manage.py seed_demo  -> creates a demo company, staff, candidate, job and coding assessment."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import CandidateProfile, Company, User
from recruitment.models import Assessment, CodingProblem, Job, JobStage, ProblemTestCase

PASSWORD = "Demo@12345"


class Command(BaseCommand):
    help = "Seed demo data (all accounts use password Demo@12345)"

    def handle(self, *args, **opts):
        if not User.objects.filter(email="admin@demo.com").exists():
            User.objects.create_superuser("admin@demo.com", PASSWORD, first_name="Platform", last_name="Admin")
        company, _ = Company.objects.get_or_create(
            name="Acme Technologies", defaults={"email": "careers@acme.com", "industry": "Software",
                                                "location": "Kochi, India", "size": "51-200"})
        staff = {}
        for email, role, first in [("companyadmin@demo.com", User.Role.COMPANY_ADMIN, "Anita"),
                                   ("hr@demo.com", User.Role.HR, "Hari"),
                                   ("interviewer@demo.com", User.Role.INTERVIEWER, "Ira")]:
            staff[role], _ = User.objects.get_or_create(email=email, defaults={
                "first_name": first, "role": role, "company": company})
            staff[role].set_password(PASSWORD)
            staff[role].save()
        cand, _ = User.objects.get_or_create(email="candidate@demo.com", defaults={
            "first_name": "Rahul", "last_name": "Kumar", "role": User.Role.CANDIDATE})
        cand.set_password(PASSWORD)
        cand.save()
        CandidateProfile.objects.get_or_create(user=cand, defaults={
            "skills": ["Python", "Django", "React", "MySQL", "Docker"], "experience_years": 2})

        job, created = Job.objects.get_or_create(
            company=company, title="Python Full Stack Developer",
            defaults={"created_by": staff[User.Role.HR], "department": "Engineering", "location": "Remote",
                      "required_skills": ["Python", "Django", "React", "REST API", "PostgreSQL"],
                      "preferred_skills": ["Docker", "AWS"], "experience_min": 1, "experience_max": 3,
                      "education": "Bachelor's degree", "status": "open",
                      "description": "Build and maintain Django + React applications.",
                      "deadline": timezone.localdate() + timedelta(days=30)})
        if created:
            for i, (n, t) in enumerate([("Resume Screening", "resume_screening"),
                                        ("Coding Assessment", "coding_assessment"),
                                        ("Technical Interview", "technical_interview"),
                                        ("HR Interview", "hr_interview"), ("Final Decision", "final_decision")], 1):
                JobStage.objects.create(job=job, name=n, stage_type=t, order=i)

        problem, created = CodingProblem.objects.get_or_create(
            company=company, title="Largest element",
            defaults={"description": "Given N integers, print the largest.", "input_format": "N then N integers",
                      "output_format": "One integer", "difficulty": "easy", "created_by": staff[User.Role.HR],
                      "examples": [{"input": "5\n10 20 5 30 15", "output": "30"}]})
        if created:
            for inp, out, hidden in [("5\n10 20 5 30 15\n", "30", False), ("3\n-5 -2 -10\n", "-2", True),
                                     ("1\n7\n", "7", True)]:
                ProblemTestCase.objects.create(problem=problem, input_data=inp, expected_output=out, is_hidden=hidden)
        assessment, _ = Assessment.objects.get_or_create(
            company=company, title="Python screening test", defaults={"job": job, "duration_minutes": 30,
                                                                      "created_by": staff[User.Role.HR]})
        assessment.problems.add(problem)
        self.stdout.write(self.style.SUCCESS(
            "Seeded. Logins (password Demo@12345): admin@demo.com, companyadmin@demo.com, hr@demo.com, "
            "interviewer@demo.com, candidate@demo.com"))
