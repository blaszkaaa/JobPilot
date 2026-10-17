"""Tests for local evidence-based CV analysis and access control."""
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("JOBPILOT_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("JOBPILOT_ADMIN_PASSWORD", "test-password-123456")
os.environ.setdefault("JOBPILOT_SESSION_SECRET", "local-tests-only-secret-key-long-enough")

from app import cv_analysis, main


class CVAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.previous = main.DB_PATH
        main.DB_PATH = Path(self.folder.name) / "test.sqlite3"
        main.initialize()
        with main.connection() as db:
            db.execute("""INSERT INTO jobs
                (id,title,company,location,remote,description,url,source,posted_at,score,reason,discovered_at,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("manual:cv:1", "Python / FastAPI Developer", "Local GmbH", "Poznań", 1,
                 "Wymagamy Python, FastAPI, Docker i PostgreSQL. Bonus: React.",
                 "https://example.org/jobs/python", "Manual", "", 79, "Python", main.current_utc(), "new"))
            db.execute("UPDATE profile SET cv_text=? WHERE id=1",
                       ("Pracowałem z Python i FastAPI przy systemach automatyzacji. "
                        "Wdrażałem usługi przy użyciu Docker i Git.",))
            db.commit()
        self.client = TestClient(main.app)
        self.client.cookies.set("jp_session", main.signed_session())

    def tearDown(self):
        self.client.close()
        main.DB_PATH = self.previous
        self.folder.cleanup()

    def test_matches_and_unconfirmed_are_explainable(self):
        response = self.client.get("/api/cv-analysis/manual:cv:1")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        matched = {x["skill"] for x in data["matched"]}
        unconfirmed = {x["skill"] for x in data["unconfirmed"]}
        self.assertEqual(matched, {"Python", "FastAPI", "Docker"})
        self.assertEqual(unconfirmed, {"PostgreSQL", "React"})
        self.assertEqual(data["coverage_percent"], 60)
        self.assertEqual(data["detected_count"], 5)
        for item in data["matched"]:
            self.assertTrue(item["job_evidence"])
            self.assertTrue(item["cv_evidence"])
        self.assertIn("nie oznacza", data["note"])

    def test_missing_cv_is_not_misrepresented_as_skill_gap(self):
        with main.connection() as db:
            db.execute("UPDATE profile SET cv_text='' WHERE id=1")
            db.commit()
        response = self.client.get("/api/cv-analysis/manual:cv:1")
        data = response.json()
        self.assertFalse(data["cv_present"])
        self.assertIsNone(data["coverage_percent"])
        self.assertEqual(data["matched"], [])
        self.assertEqual(data["unconfirmed"], [])
        self.assertEqual(data["detected_count"], 5)

    def test_no_detected_skills_has_no_percent(self):
        result = cv_analysis.analyze({
            "id": "a", "title": "Specjalista ds. marketingu",
            "company": "Test", "description": "Praca przy organizacji spotkań."
        }, "Moje doświadczenie obejmuje przygotowanie opisów, spotkania i kontakt z klientem.")
        self.assertEqual(result["mentioned"], [])
        self.assertIsNone(result["coverage_percent"])
        self.assertEqual(result["unconfirmed"], [])

    def test_exact_skill_boundaries(self):
        result = cv_analysis.analyze({
            "id": "a", "title": "Django Developer",
            "company": "Test", "description": "Wymagamy Django i C++ oraz .NET"
        }, "Moje doświadczenie obejmuje Django oraz C++ i .NET w firmie.")
        found = {x["skill"] for x in result["matched"]}
        self.assertIn("Django", found)
        self.assertIn("C++", found)
        self.assertIn(".NET", found)
        self.assertNotIn("Go", result["mentioned"])
        self.assertNotIn("C#", result["mentioned"])

    def test_invalid_job_and_private_access(self):
        self.assertEqual(self.client.get("/api/cv-analysis/missing").status_code, 404)
        guest = TestClient(main.app)
        self.assertEqual(guest.get("/api/cv-analysis/manual:cv:1").status_code, 401)


if __name__ == "__main__":
    unittest.main()
