"""Private CV upload/download/delete. PDF bytes never belong in the git repository.

This uses the existing SQLite volume. No OCR and no external document service.
"""
import hashlib
import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pypdf import PdfReader

from . import main

router = APIRouter(prefix="/api", dependencies=[Depends(main.authenticated)])
MAX_PDF_BYTES = 2 * 1024 * 1024
MAX_PAGES = 12


def initialize_cv_storage():
    with main.connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS stored_cv (
            id INTEGER PRIMARY KEY CHECK(id=1),
            filename TEXT NOT NULL,
            pdf_blob BLOB NOT NULL,
            sha256 TEXT NOT NULL,
            pages INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        )""")
        db.commit()


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Nieprawidłowy plik PDF")
    if len(data) > MAX_PDF_BYTES or len(data) < 100:
        raise HTTPException(413 if len(data) > MAX_PDF_BYTES else 422,
                            "Plik PDF musi mieć do 2 MB")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ValueError("encrypted")
        pages = len(reader.pages)
        if not 1 <= pages <= MAX_PAGES:
            raise ValueError("page limit")
        cv_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        raise HTTPException(422, "Nie udało się odczytać PDF (do 12 stron, bez hasła)")
    cv_text = re.sub(r"\n{3,}", "\n\n", cv_text).strip()[:20000]
    if len(cv_text) < 30:
        raise HTTPException(422, "PDF nie ma czytelnego tekstu. Skan wymaga OCR.")
    return cv_text, pages


def safe_filename(header: str) -> str:
    text = header.split("/")[-1].split("\\")[-1].strip()
    text = re.sub(r"[^a-zA-Z0-9._ -]", "_", text)[:100].strip(" .")
    if not text or text in (".", ".."):
        text = "cv.pdf"
    if not text.lower().endswith(".pdf"):
        text = text + ".pdf"
    return text


@router.get("/profile/cv/file")
def cv_metadata():
    with main.connection() as db:
        row = db.execute(
            "SELECT filename,sha256,pages,uploaded_at,length(pdf_blob) AS size_bytes FROM stored_cv WHERE id=1"
        ).fetchone()
    return {"exists": row is not None, "file": dict(row) if row is not None else None}


@router.post("/profile/cv/file")
async def upload_cv(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/pdf":
        raise HTTPException(415, "Prześlij plik PDF")
    size = request.headers.get("content-length", "")
    if size.isdigit() and int(size) > MAX_PDF_BYTES:
        raise HTTPException(413, "Plik przekracza 2 MB")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(413, "Plik przekracza 2 MB")
    raw = bytes(data)
    text, pages = extract_pdf_text(raw)
    filename = safe_filename(request.headers.get("x-cv-filename", "cv.pdf"))
    now = main.current_utc()
    digest = hashlib.sha256(raw).hexdigest()
    with main.connection() as db:
        db.execute("""INSERT INTO stored_cv(id,filename,pdf_blob,sha256,pages,uploaded_at)
            VALUES (1,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                filename=excluded.filename,pdf_blob=excluded.pdf_blob,sha256=excluded.sha256,
                pages=excluded.pages,uploaded_at=excluded.uploaded_at
        """, (filename, raw, digest, pages, now))
        # Update the very same profile CV string used by ranking and CV analysis.
        # All existing preferences and profile fields stay unchanged.
        db.execute("UPDATE profile SET cv_text=? WHERE id=1", (text,))
        db.commit()
    # Recalculate cached scores, but preserve job statuses and user feedback.
    from .learning import recompute
    recompute()
    return {"ok": True, "filename": filename, "pages": pages, "size_bytes": len(raw),
            "sha256": digest, "uploaded_at": now, "text_length": len(text)}


@router.get("/profile/cv/file/download")
def download_cv():
    with main.connection() as db:
        row = db.execute("SELECT filename,pdf_blob FROM stored_cv WHERE id=1").fetchone()
    if row is None:
        raise HTTPException(404, "Nie zapisano pliku CV")
    # Filename only contains allowlisted ASCII characters; prevent response splitting.
    filename = safe_filename(row["filename"])
    return Response(content=row["pdf_blob"], media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/profile/cv/file")
def delete_cv_file():
    with main.connection() as db:
        deleted = db.execute("DELETE FROM stored_cv WHERE id=1").rowcount
        db.commit()
    if not deleted:
        raise HTTPException(404, "Nie zapisano pliku CV")
    # Only the file is deleted; already-extracted text in the profile remains.
    return {"ok": True, "text_retained": True}
