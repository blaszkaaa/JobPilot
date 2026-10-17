"""Source management and manual-offer integration tests."""
import asyncio
import os
import tempfile
import httpx
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

os.environ.setdefault("JOBPILOT_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("JOBPILOT_ADMIN_PASSWORD", "test-password-123456")
os.environ.setdefault("JOBPILOT_SESSION_SECRET", "local-tests-only-secret-key-long-enough")

from app import main, sources


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = main.DB_PATH
        self.greenhouse = main.GREENHOUSE_BOARDS
        self.lever = main.LEVER_SITES
        main.GREENHOUSE_BOARDS = ["fixture-env"]
        main.LEVER_SITES = []
        main.DB_PATH = Path(self.temp.name) / "sources.sqlite3"
        main.initialize()
        main.initialize()  # migration stays idempotent
        self.client = TestClient(main.app)
        self.client.cookies.set("jp_session", main.signed_session())

    def tearDown(self):
        self.client.close()
        main.DB_PATH = self.previous_db
        main.GREENHOUSE_BOARDS = self.greenhouse
        main.LEVER_SITES = self.lever
        self.temp.cleanup()

    def test_add_pause_resume_and_remove_source(self):
        existing = self.client.get("/api/sources").json()
        self.assertTrue(any(b["slug"] == "fixture-env" and not b["managed"]
                            for b in existing["boards"]))
        created = self.client.post("/api/sources", json={
            "provider": "greenhouse", "slug": "New_Company", "label": "New Co",
            "enabled": True
        })
        self.assertEqual(created.status_code, 201, created.text)
        source_id = created.json()["id"]
        self.assertIn("new_company", sources.resolve_boards("greenhouse"))
        self.assertEqual(sources.resolve_boards("greenhouse").count("new_company"), 1)
        dup = self.client.post("/api/sources", json={
            "provider": "greenhouse", "slug": "new_company", "label": "Duplicate"
        })
        self.assertEqual(dup.status_code, 409)
        paused = self.client.patch(f"/api/sources/{source_id}", json={"enabled": False})
        self.assertEqual(paused.status_code, 200)
        self.assertNotIn("new_company", sources.resolve_boards("greenhouse"))
        self.assertIn("fixture-env", sources.resolve_boards("greenhouse"))
        self.assertEqual(self.client.patch(f"/api/sources/{source_id}",
                                           json={"enabled": True}).status_code, 200)
        self.assertIn("new_company", sources.resolve_boards("greenhouse"))
        self.assertEqual(self.client.delete(f"/api/sources/{source_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/sources/{source_id}").status_code, 404)

    def test_source_validations(self):
        for slug in ["evil/../name", "https://example.com", ".", "@bad", "x"]:
            response = self.client.post("/api/sources", json={
                "provider": "lever", "slug": slug, "label": "Test"
            })
            self.assertEqual(response.status_code, 422, (slug, response.text))
        self.assertEqual(self.client.post("/api/sources", json={
            "provider": "unsupported", "slug": "company"
        }).status_code, 422)
        self.assertEqual(self.client.patch("/api/sources/777",
                                            json={"enabled": False}).status_code, 404)

    def test_manually_add_job_and_reject_duplicates(self):
        body = {
            "title": "Python Automation Developer", "company": "Example GmbH",
            "location": "Poznań", "remote": True,
            "description": "We need Python API development experience and automation skills.",
            "url": "https://jobs.example.org/careers/python-automation"
        }
        response = self.client.post("/api/jobs/manual", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()["job_id"].startswith("manual:"))
        self.assertGreaterEqual(response.json()["score"], 0)
        self.assertEqual(self.client.post("/api/jobs/manual", json=body).status_code, 409)
        listings = self.client.get("/api/jobs").json()
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["source"], "Manual")
        self.assertEqual(listings[0]["url"], body["url"])
        self.assertEqual(listings[0]["remote"], True)
        # Manual job works in application pipeline.
        prepared = self.client.post("/api/applications/prepare",
                                    json={"job_id": response.json()["job_id"]})
        self.assertEqual(prepared.status_code, 201, prepared.text)

    def test_disallow_non_https_and_unsafe_urls(self):
        template = {
            "title": "Python Developer", "company": "Acme",
            "description": "A long enough description for a legitimate job listing.",
            "location": "Remote", "remote": True
        }
        for url in [
            "javascript:alert(1)", "http://example.com/listing",
            "https://localhost/private", "https://127.0.0.1/private",
            "https://evil@public.example.com/listing", "https://foo.internal/a",
            "https://8.8.8.8/listing"
        ]:
            reply = self.client.post("/api/jobs/manual", json={**template, "url": url})
            self.assertIn(reply.status_code, (422,), (url, reply.text))

    def test_concurrent_sources_and_isolated_provider_failure(self):
        main.GREENHOUSE_BOARDS = ["working-board", "failed-board"]
        main.LEVER_SITES = ["my-lever"]
        metrics = {"active": 0, "peak": 0}
        class FakeResponse:
            def __init__(self, body):
                self.body = body
            def raise_for_status(self):
                return None
            def json(self):
                return self.body

        class FakeClient:
            async def get(self, url, params=None):
                if "arbeitnow" in url:
                    return FakeResponse({"data": []})
                metrics["active"] += 1
                metrics["peak"] = max(metrics["peak"], metrics["active"])
                try:
                    await asyncio.sleep(0.01)
                    if "failed-board" in url:
                        raise httpx.HTTPError("unavailable")
                    if "greenhouse" in url:
                        return FakeResponse({"jobs": [{
                            "id": 1, "title": "Python engineer",
                            "location": {"name": "Remote"},
                            "absolute_url": "https://boards.greenhouse.io/working-board/jobs/1"
                        }]})
                    return FakeResponse([{
                        "id": "lever-1", "text": "Backend developer",
                        "categories": {"location": "Remote"},
                        "hostedUrl": "https://jobs.lever.co/my-lever/lever-1"
                    }])
                finally:
                    metrics["active"] -= 1

        jobs, errors = asyncio.run(main.fetch_jobs(FakeClient()))
        self.assertEqual(len(jobs), 2)
        self.assertGreaterEqual(metrics["peak"], 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("failed-board", errors[0])
        self.assertEqual({j["source"] for j in jobs}, {"Greenhouse", "Lever"})

    def test_no_guest_access(self):
        guest = TestClient(main.app)
        self.assertEqual(guest.get("/api/sources").status_code, 401)
        self.assertEqual(guest.post("/api/sources", json={
            "provider": "lever", "slug": "example"
        }).status_code, 401)
        self.assertEqual(guest.post("/api/jobs/manual", json={
            "title": "Role", "company": "Example",
            "description": "Valid sufficiently long job description for test",
            "url": "https://example.com"
        }).status_code, 401)


if __name__ == "__main__":
    unittest.main()
