import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

PWD = "Str0ng!Passw0rd#1"
RESUME = b"""Rahul Kumar
rahul@example.com
Skills
Python, Django, React, PostgreSQL, Docker, REST API
Experience
Software Engineer 2022 - Present
Education
B.Tech in Computer Science
"""


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class HiringFlowTests(APITestCase):
    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_full_flow(self):
        # company registration (company admin) ---------------------------------
        r = self.client.post("/api/auth/register/company/", {
            "company_name": "Acme", "company_email": "c@acme.com", "first_name": "Anita",
            "email": "admin@acme.com", "password": PWD}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.auth(r.data["access"])

        # job ----------------------------------------------------------------
        r = self.client.post("/api/jobs/", {
            "title": "Python Dev", "description": "Build APIs", "experience_min": 1,
            "required_skills": ["python", "django", "react", "postgres"], "status": "open"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        job_id = r.data["id"]
        self.assertEqual(len(r.data["stages"]), 5)

        # candidate: register, upload resume, apply ---------------------------------
        self.client.credentials()
        r = self.client.post("/api/auth/register/candidate/", {
            "email": "rahul@example.com", "password": PWD, "first_name": "Rahul"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.auth(r.data["access"])
        r = self.client.post("/api/resumes/", {"file": SimpleUploadedFile("resume.txt", RESUME)}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("Django", r.data["skills"])
        r = self.client.post("/api/applications/", {"job": job_id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn("overall_match", r.data)  # AI scoring hidden from candidates
        app_id = r.data["id"]

        # HR sees AI screening result --------------------------------------------
        self.client.credentials()
        r = self.client.post("/api/auth/login/", {"email": "admin@acme.com", "password": PWD}, format="json")
        self.assertEqual(r.status_code, 200)
        self.auth(r.data["access"])
        r = self.client.get("/api/applications/")
        self.assertEqual(r.data["results"][0]["status"], "screening")
        self.assertGreater(r.data["results"][0]["overall_match"], 70)
        r = self.client.post(f"/api/applications/{app_id}/shortlist/")
        self.assertEqual(r.data["status"], "shortlisted")

        # coding assessment -------------------------------------------------------
        r = self.client.post("/api/coding-problems/", {
            "title": "Max", "description": "Print the max", "test_cases": [
                {"input_data": "3\n1 5 2\n", "expected_output": "5", "is_hidden": False},
                {"input_data": "2\n-1 -7\n", "expected_output": "-1", "is_hidden": True}]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.post("/api/assessments/", {"title": "Screen", "problem_ids": [r.data["id"]]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        assessment_id = r.data["id"]
        r = self.client.post(f"/api/assessments/{assessment_id}/assign/", {"application_ids": [app_id]}, format="json")
        self.assertEqual(r.data["assigned"], 1)
        attempt_id = r.data["attempt_ids"][0]

        self.client.credentials()
        r = self.client.post("/api/auth/login/", {"email": "rahul@example.com", "password": PWD}, format="json")
        self.auth(r.data["access"])
        self.assertEqual(self.client.post(f"/api/assessment-attempts/{attempt_id}/start/").status_code, 200)
        problems = self.client.get(f"/api/assessment-attempts/{attempt_id}/problems/").data
        r = self.client.post(f"/api/assessment-attempts/{attempt_id}/submit-code/", {
            "problem": problems[0]["id"], "language": "python",
            "code": "input()\nprint(max(map(int, input().split())))"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["verdict"], "accepted")
        r = self.client.post(f"/api/assessment-attempts/{attempt_id}/finish/")
        self.assertEqual(r.data["score"], 100.0)

        # dashboard ---------------------------------------------------------------
        self.client.credentials()
        r = self.client.post("/api/auth/login/", {"email": "admin@acme.com", "password": PWD}, format="json")
        self.auth(r.data["access"])
        r = self.client.get("/api/analytics/dashboard/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["totals"]["applications"], 1)
        r = self.client.get(f"/api/applications/{app_id}/scorecard/")
        self.assertEqual(r.data["coding_score"], 100.0)

    def test_candidate_cannot_create_jobs(self):
        r = self.client.post("/api/auth/register/candidate/", {
            "email": "x@example.com", "password": PWD, "first_name": "X"}, format="json")
        self.auth(r.data["access"])
        self.assertEqual(self.client.post("/api/jobs/", {}, format="json").status_code, 403)


class CandidatePortfolioTests(APITestCase):
    def setUp(self):
        response = self.client.post("/api/auth/register/candidate/", {
            "email": "portfolio@example.com",
            "password": PWD,
            "first_name": "Port",
            "last_name": "Folio",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.candidate_id = response.data["user"]["id"]
        self.access = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_project_crud_and_public_visibility(self):
        response = self.client.post("/api/candidate-projects/", {
            "title": "Portfolio site",
            "description": "A demo project",
            "technologies": '["React", "Django"]',
            "github_url": "https://github.com/example/portfolio",
            "live_demo_url": "https://example.com",
            "featured": "true",
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        project_id = response.data["id"]
        response = self.client.post("/api/candidate-projects/", {
            "title": "Featured replacement",
            "technologies": '["Vite"]',
            "featured": "true",
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        featured_id = response.data["id"]
        projects = self.client.get("/api/candidate-projects/").data
        self.assertEqual([item["id"] for item in projects if item["featured"]], [featured_id])

        response = self.client.get(f"/api/public/candidates/{self.candidate_id}/")
        self.assertEqual(response.status_code, 404)

        response = self.client.patch("/api/candidate-profile/", {
            "headline": "Full-stack developer",
            "is_public": True,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        self.client.credentials()
        response = self.client.get(f"/api/public/candidates/{self.candidate_id}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["candidate_name"], "Port Folio")
        projects_by_id = {project["id"]: project for project in response.data["projects"]}
        self.assertEqual(projects_by_id[project_id]["technologies"], ["React", "Django"])
        self.assertEqual(projects_by_id[featured_id]["featured"], True)

    def test_social_links_require_matching_domains(self):
        response = self.client.patch("/api/candidate-profile/", {
            "github": "https://example.com/not-github",
        }, format="json")
        self.assertEqual(response.status_code, 400)
