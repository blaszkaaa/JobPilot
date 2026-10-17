"""Integration tests for the search-watch and applicant workflow."""
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("JOBPILOT_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("JOBPILOT_ADMIN_PASSWORD", "test-password-123456")
os.environ.setdefault("JOBPILOT_SESSION_SECRET", "local-tests-only-secret-key-long-enough")

from app import main, features


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = main.DB_PATH
        main.DB_PATH = Path(self.tmp.name) / "tests.sqlite3"
        main.initialize()
        self.client = TestClient(main.app)
        self.client.cookies.set("jp_session", main.signed_session())
        with main.connection() as db:
            db.execute("""INSERT INTO jobs
                (id,title,company,location,remote,description,url,source,
                 posted_at,score,reason,discovered_at,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("test:100", "Backend Python", "=Sample Ltd", "Warszawa",
                 1, "Python, FastAPI, Docker", "https://example.com/jobs/100",
                 "Fixture", "", 87, "Pasuje Python", main.current_utc(), "new"))
            db.commit()

    def tearDown(self):
        self.client.close()
        main.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_requires_session(self):
        client = TestClient(main.app)
        self.assertEqual(client.get("/api/watches").status_code, 401)
        self.assertEqual(client.post("/api/applications/prepare", json={"job_id": "test:100"}).status_code, 401)

    def test_watches_crud_and_limit(self):
        for i in range(5):
            response = self.client.post("/api/watches", json={
                "name": f"Python {i}", "query": "Python", "location": "Poznań",
                "enabled": True})
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(self.client.get("/api/watches").json()), 5)
        watches, count = features.active_watches()
        self.assertEqual(count, 5)
        self.assertEqual(len(watches), 5)
        self.assertEqual(self.client.post("/api/watches", json={
            "name": "Extra", "query": "Extra", "location": ""
        }).status_code, 400)
        item_id = self.client.get("/api/watches").json()[0]["id"]
        self.assertEqual(self.client.put(f"/api/watches/{item_id}", json={
            "name": "Disabled", "query": "API", "location": "", "enabled": False
        }).status_code, 200)
        watches, count = features.active_watches()
        self.assertEqual(len(watches), 4)
        self.assertEqual(self.client.delete(f"/api/watches/{item_id}").status_code, 200)

    def test_application_draft_and_manual_confirmation(self):
        response = self.client.post("/api/applications/prepare", json={"job_id": "test:100"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()["created"])
        app_id = response.json()["id"]
        prepared = self.client.get("/api/applications/pipeline").json()
        self.assertEqual(prepared[0]["status"], "draft")
        self.assertIn("Backend Python", prepared[0]["letter"])
        self.assertEqual(main.stats()["applied"], 0)  # Drafts are not real applications.
        # Repeated preparation must preserve status and existing note.
        body = {
            "status": "applied", "notes": "Wysłano na oficjalnej stronie", "letter": "moja treść",
            "follow_up": "2026-11-01"
        }
        saved = self.client.patch(f"/api/applications/pipeline/{app_id}", json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.post("/api/applications/prepare", json={"job_id": "test:100"}).json()["created"], False)
        after = self.client.get("/api/applications/pipeline").json()[0]
        self.assertEqual(after["status"], "applied")
        self.assertEqual(after["follow_up"], "2026-11-01")
        self.assertEqual(after["notes"], "Wysłano na oficjalnej stronie")
        self.assertEqual(main.stats()["applied"], 1)
        history = self.client.get(f"/api/applications/pipeline/{app_id}/events").json()
        self.assertEqual(len(history), 2)
        self.assertIn("potwierdził", history[0]["event"])
        self.assertEqual(self.client.delete(f"/api/applications/pipeline/{app_id}").status_code, 200)

    def test_followup_alert_is_sent_once(self):
        prepared = self.client.post("/api/applications/prepare", json={"job_id": "test:100"}).json()
        app_id = prepared["id"]
        response = self.client.patch(f"/api/applications/pipeline/{app_id}", json={
            "status": "interview", "follow_up": "2026-01-01",
            "notes": "", "letter": "Example"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(features.queue_due_followups()), 1)
        self.assertEqual(len(features.queue_due_followups()), 0)
        notices = self.client.get("/api/notifications").json()
        self.assertTrue(any("Przypomnienie" in n["message"] for n in notices))

    def test_invalid_stage_and_cv_import(self):
        response = self.client.post("/api/applications/prepare", json={"job_id": "unknown"})
        self.assertEqual(response.status_code, 404)
        response = self.client.post("/api/profile/cv/pdf",
                                    data=b"<html>Not a PDF</html>",
                                    headers={"Content-Type": "application/pdf"})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/profile/cv/pdf",
                                    data=b"%PDF-" + b"x" * (2 * 1024 * 1024),
                                    headers={"Content-Type": "application/pdf"})
        self.assertEqual(response.status_code, 413)

    def test_csv_export_blocks_formulas(self):
        self.assertEqual(features.csv_cell("=1+1"), "'=1+1")
        self.assertEqual(features.csv_cell(" +cmd"), "' +cmd")
        self.assertEqual(features.csv_cell("Python"), "Python")
        self.client.post("/api/applications/prepare", json={"job_id": "test:100"})
        response = self.client.get("/api/applications/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=Sample Ltd", response.text)
        self.assertIn("filename=", response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
