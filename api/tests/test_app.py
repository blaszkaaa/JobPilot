import os
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("JOBPILOT_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("JOBPILOT_ADMIN_PASSWORD", "test-password-123456")
os.environ.setdefault("JOBPILOT_SESSION_SECRET", "local-tests-only-secret-key-long-enough")

from app import main


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "full_name": "", "keywords": "Python, FastAPI", "cv_text": "REST API Python developer",
            "location": "Warszawa", "excluded": "", "remote_only": False, "min_score": 60
        }
        self.jobs = [{
            "id": "test:1", "title": "Python / FastAPI Developer", "company": "Sample",
            "location": "Warszawa", "description": "We need Python FastAPI skills.",
            "remote": False, "url": "https://example.com/job", "source": "Test",
            "posted_at": ""
        }]

    def test_relevant_job_scores_positive(self):
        output = main.rank(self.jobs, self.profile)
        self.assertGreater(output[0]["score"], 30)
        self.assertIn("python", output[0]["reason"].lower())

    def test_remote_only_blocks_office_job(self):
        self.profile["remote_only"] = True
        self.assertEqual(main.rank(self.jobs, self.profile)[0]["score"], 0)

    def test_excluded_keyword_blocks_job(self):
        self.profile["excluded"] = "Developer"
        self.assertEqual(main.rank(self.jobs, self.profile)[0]["score"], 0)

    def test_strips_markup(self):
        self.assertEqual(main.plain("<p>Python <b>jobs</b></p>"), "Python jobs")

    def test_rejects_non_https_links(self):
        self.assertEqual(main.safe_url("javascript:alert(1)"), "")
        self.assertEqual(main.safe_url("http://example.com"), "")

    def test_signed_session(self):
        self.assertEqual(main.signed_session().count(":"), 2)


class PersistenceTests(unittest.TestCase):
    def test_database_initialization(self):
        with tempfile.TemporaryDirectory() as path:
            old = main.DB_PATH
            main.DB_PATH = Path(path) / "jobs.sqlite3"
            try:
                main.initialize()
                self.assertEqual(main.profile_dict()["location"], "Polska")
            finally:
                main.DB_PATH = old


class RefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_persists_fetched_job(self):
        async def fetch_one_job(_client):
            return ([{
                "id": "test:refresh", "title": "Python Developer", "company": "Sample",
                "location": "Polska", "description": "Python and FastAPI work",
                "remote": True, "url": "https://example.com/job", "source": "Test",
                "posted_at": "",
            }], [])

        with tempfile.TemporaryDirectory() as path:
            old = main.DB_PATH
            main.DB_PATH = Path(path) / "jobs.sqlite3"
            try:
                main.initialize()
                with patch.object(main, "fetch_jobs", fetch_one_job):
                    result = await main.refresh()
                self.assertEqual(result["count"], 1)
                with main.connection() as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
                del db
                gc.collect()
            finally:
                main.DB_PATH = old


if __name__ == "__main__":
    unittest.main()
