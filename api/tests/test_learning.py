"""Regression tests for user-controlled recommendations and inbox state."""
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("JOBPILOT_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("JOBPILOT_ADMIN_PASSWORD", "test-password-123456")
os.environ.setdefault("JOBPILOT_SESSION_SECRET", "local-tests-only-secret-key-long-enough")

from app import intelligence, main


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = main.DB_PATH
        main.DB_PATH = Path(self.temp.name) / "test.sqlite3"
        main.initialize()
        with main.connection() as db:
            for id_, title, description in [
                ("fixture:1", "Python Developer", "Python FastAPI REST APIs backend development"),
                ("fixture:2", "Python Backend Engineer", "FastAPI REST APIs backend development Python"),
                ("fixture:3", "Marketing Manager", "advertising media sales campaign communication"),
            ]:
                db.execute("""INSERT INTO jobs(id,title,company,location,remote,description,
                    url,source,posted_at,score,reason,discovered_at,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (id_, title, "Acme", "Remote", 1, description,
                     "https://example.com/" + id_, "Test", "", 40, "", main.current_utc(), "new"))
            db.execute("INSERT INTO notifications(job_id,message,created_at) VALUES (?,?,?)",
                       ("fixture:1", "Nowa oferta", main.current_utc()))
            db.execute("INSERT INTO scan_history(scanned_at,fetched,new_matches,errors) VALUES (?,?,?,?)",
                       (main.current_utc(), 3, 2, None))
            db.commit()
        self.client = TestClient(main.app)
        self.client.cookies.set("jp_session", main.signed_session())

    def tearDown(self):
        self.client.close()
        main.DB_PATH = self.previous
        self.temp.cleanup()

    def test_model_adjusts_to_user_dislike_and_undo(self):
        before = {j["id"]: j["score"] for j in self.client.get("/api/jobs").json()}
        res = self.client.post("/api/jobs/fixture:1/feedback", json={"opinion": "dislike"})
        self.assertEqual(res.status_code, 200, res.text)
        after = {j["id"]: j for j in self.client.get("/api/jobs").json()}
        self.assertLess(after["fixture:2"]["score"], before["fixture:2"] + 10)
        self.assertIn("niechcianych", after["fixture:2"]["reason"])
        self.assertEqual(after["fixture:1"]["feedback"], -1)
        self.assertEqual(self.client.get("/api/stats").json()["dislikes"], 1)
        clear = self.client.post("/api/jobs/fixture:1/feedback", json={"opinion": "clear"})
        self.assertEqual(clear.status_code, 200)
        self.assertEqual(self.client.get("/api/stats").json()["dislikes"], 0)

    def test_ranking_similarity_penalty(self):
        profile = main.profile_dict()
        with main.connection() as db:
            jobs = [dict(j) for j in db.execute("SELECT * FROM jobs ORDER BY id")]
        a = intelligence.rank(jobs, profile)
        b = intelligence.rank(jobs, profile, [{**jobs[0], "opinion": -1}])
        self.assertLess(b[1]["score"], a[1]["score"])
        self.assertEqual(a[0]["score"], b[0]["score"])  # own rating not used for own score

    def test_notification_read_state_and_scan_history(self):
        notices = self.client.get("/api/notifications").json()
        self.assertEqual(len(notices), 1)
        self.assertIsNone(notices[0]["read_at"])
        self.assertEqual(self.client.get("/api/stats").json()["unread"], 1)
        self.assertEqual(self.client.patch(f"/api/notifications/{notices[0]['id']}/read").status_code, 200)
        self.assertEqual(self.client.get("/api/stats").json()["unread"], 0)
        self.assertEqual(self.client.post("/api/notifications/read-all").json()["changed"], 0)
        scans = self.client.get("/api/scans").json()
        self.assertEqual(scans[0]["fetched"], 3)
        self.assertEqual(scans[0]["new_matches"], 2)

    def test_invalid_opinion_and_unauthorized_routes(self):
        self.assertEqual(self.client.post("/api/jobs/fixture:1/feedback",
                                          json={"opinion": "maybe"}).status_code, 422)
        self.assertEqual(self.client.post("/api/jobs/missing/feedback",
                                          json={"opinion": "like"}).status_code, 404)
        guest = TestClient(main.app)
        self.assertEqual(guest.get("/api/scans").status_code, 401)
        self.assertEqual(guest.post("/api/notifications/read-all").status_code, 401)


if __name__ == "__main__":
    unittest.main()
