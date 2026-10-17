"""Private PDF persistence and access controls."""
import io
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

os.environ.setdefault("JOBPILOT_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("JOBPILOT_ADMIN_PASSWORD", "test-password-123456")
os.environ.setdefault("JOBPILOT_SESSION_SECRET", "local-tests-only-secret-key-long-enough")
from app import main


def test_pdf() -> bytes:
    """A tiny generated PDF containing text, no personal data."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    # Add standard font resources and a content stream, no external PDF fixtures.
    resources = DictionaryObject()
    fonts = DictionaryObject()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica")
    })
    font_ref = writer._add_object(font)
    fonts[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 60 750 Td (Python UiPath RPA automation developer and SQL experience) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class CVStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.previous = main.DB_PATH
        main.DB_PATH = Path(self.folder.name) / "cv.sqlite3"
        main.initialize()
        self.client = TestClient(main.app)
        self.client.cookies.set("jp_session", main.signed_session())
        self.pdf = test_pdf()

    def tearDown(self):
        self.client.close()
        main.DB_PATH = self.previous
        self.folder.cleanup()

    def test_upload_retains_pdf_and_updates_profile(self):
        self.assertFalse(self.client.get("/api/profile/cv/file").json()["exists"])
        reply = self.client.post("/api/profile/cv/file", content=self.pdf,
                                 headers={"Content-Type": "application/pdf",
                                          "X-CV-Filename": "My Resume.pdf"})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json()["pages"], 1)
        self.assertGreater(reply.json()["text_length"], 30)
        self.assertTrue(self.client.get("/api/profile/cv/file").json()["exists"])
        self.assertIn("UiPath", self.client.get("/api/profile").json()["cv_text"])
        download = self.client.get("/api/profile/cv/file/download")
        self.assertEqual(download.content, self.pdf)
        self.assertIn('filename="My Resume.pdf"', download.headers["content-disposition"])
        self.assertEqual(download.headers["cache-control"], "no-store")

    def test_replacing_and_deleting_file_keeps_extracted_text(self):
        self.assertEqual(self.client.post("/api/profile/cv/file", content=self.pdf,
                                          headers={"Content-Type": "application/pdf"}).status_code, 200)
        second = self.client.post("/api/profile/cv/file", content=self.pdf,
                                  headers={"Content-Type": "application/pdf",
                                           "X-CV-Filename": "../../uploaded.pdf"})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.client.get("/api/profile/cv/file").json()["file"]["filename"], "uploaded.pdf")
        removed = self.client.delete("/api/profile/cv/file")
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["text_retained"])
        self.assertIn("Python", self.client.get("/api/profile").json()["cv_text"])
        self.assertEqual(self.client.get("/api/profile/cv/file/download").status_code, 404)
        self.assertEqual(self.client.delete("/api/profile/cv/file").status_code, 404)

    def test_invalid_content_and_limit(self):
        self.assertEqual(self.client.post("/api/profile/cv/file",
                                          content=b"not pdf", headers={"Content-Type": "application/pdf"}).status_code, 422)
        self.assertEqual(self.client.post("/api/profile/cv/file",
                                          content=b"x" * (2 * 1024 * 1024 + 1),
                                          headers={"Content-Type": "application/pdf"}).status_code, 413)
        self.assertEqual(self.client.post("/api/profile/cv/file",
                                          content=self.pdf, headers={"Content-Type": "text/plain"}).status_code, 415)
        self.assertFalse(self.client.get("/api/profile/cv/file").json()["exists"])

    def test_login_required(self):
        guest = TestClient(main.app)
        self.assertEqual(guest.get("/api/profile/cv/file").status_code, 401)
        self.assertEqual(guest.get("/api/profile/cv/file/download").status_code, 401)
        self.assertEqual(guest.delete("/api/profile/cv/file").status_code, 401)
        self.assertEqual(guest.post("/api/profile/cv/file", content=self.pdf,
                                    headers={"Content-Type": "application/pdf"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
