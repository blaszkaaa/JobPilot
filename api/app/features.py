"""Search watches and application workspace. All submissions require user action on the employer's website."""
import csv
import io
import os
import re
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import main

router = APIRouter(prefix="/api", dependencies=[Depends(main.authenticated)])
STAGES = ("draft", "applied", "interview", "offer", "rejected", "withdrawn")
MAX_SEARCHES = 5
MAX_PDF_BYTES = 2 * 1024 * 1024


class Watch(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    query: str = Field(min_length=2, max_length=120)
    location: str = Field(default="", max_length=100)
    enabled: bool = True


class ApplicationPreparation(BaseModel):
    job_id: str = Field(min_length=1, max_length=250)


class ApplicationUpdate(BaseModel):
    status: Literal["draft", "applied", "interview", "offer", "rejected", "withdrawn"]
    notes: str = Field(default="", max_length=4000)
    follow_up: date | None = None
    letter: str = Field(default="", max_length=6000)


def initialize_features():
    """Idempotent schema extension for databases from v0.1."""
    with main.connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, query TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL,
            stage TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id))""")
        fields = {row["name"] for row in db.execute("PRAGMA table_info(applications)")}
        for col, spec in {
            "notes": "TEXT NOT NULL DEFAULT ''",
            "follow_up": "TEXT",
            "letter": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT",
        }.items():
            if col not in fields:
                db.execute(f"ALTER TABLE applications ADD COLUMN {col} {spec}")
        db.execute("UPDATE applications SET status='applied' WHERE status='manual'")
        db.execute("UPDATE applications SET updated_at=created_at WHERE updated_at IS NULL")
        db.commit()


def active_watches():
    with main.connection() as db:
        result = [dict(r) for r in db.execute(
            "SELECT query, location FROM watches WHERE enabled=1 ORDER BY id LIMIT ?", (MAX_SEARCHES,))]
        count = db.execute("SELECT count(*) FROM watches").fetchone()[0]
    return result, count


@router.get("/watches")
def list_watches():
    with main.connection() as db:
        return [dict(r) | {"enabled": bool(r["enabled"])} for r in db.execute(
            "SELECT * FROM watches ORDER BY id DESC")]


@router.post("/watches", status_code=201)
def create_watch(body: Watch):
    with main.connection() as db:
        if db.execute("SELECT count(*) FROM watches").fetchone()[0] >= MAX_SEARCHES:
            raise HTTPException(400, f"Maksymalnie {MAX_SEARCHES} aktywnych konfiguracji wyszukiwania")
        cur = db.execute(
            "INSERT INTO watches (name,query,location,enabled,created_at) VALUES (?,?,?,?,?)",
            (body.name.strip(), body.query.strip(), body.location.strip(), int(body.enabled), main.current_utc()))
        db.commit()
        return {"id": cur.lastrowid, **body.model_dump()}


@router.put("/watches/{watch_id}")
def update_watch(watch_id: int, body: Watch):
    with main.connection() as db:
        if db.execute("SELECT 1 FROM watches WHERE id=?", (watch_id,)).fetchone() is None:
            raise HTTPException(404, "Nie znaleziono wyszukiwania")
        db.execute(
            "UPDATE watches SET name=?,query=?,location=?,enabled=? WHERE id=?",
            (body.name.strip(), body.query.strip(), body.location.strip(), int(body.enabled), watch_id))
        db.commit()
    return {"ok": True}


@router.delete("/watches/{watch_id}")
def delete_watch(watch_id: int):
    with main.connection() as db:
        cur = db.execute("DELETE FROM watches WHERE id=?", (watch_id,))
        db.commit()
    if not cur.rowcount:
        raise HTTPException(404, "Nie znaleziono wyszukiwania")
    return {"ok": True}


def letter_for(job, profile):
    """Editable factual template, no invented experience, never sent by the service."""
    name = profile.get("full_name") or "[Imię i nazwisko]"
    skills = ", ".join(main.split_terms(profile.get("keywords") or "")) or "[umiejętności]"
    return (
        f"Dzień dobry,\n\nZgłaszam swoją kandydaturę na stanowisko {job['title']} "
        f"w firmie {job['company']}.\n\n"
        f"Zajmuję się zagadnieniami takimi jak: {skills}. "
        "Chętnie opowiem więcej o swoim doświadczeniu podczas rozmowy.\n\n"
        f"Z poważaniem,\n{name}"
    )


def get_pipeline():
    with main.connection() as db:
        return [dict(r) for r in db.execute("""
            SELECT a.id,a.job_id,a.status,a.created_at,a.updated_at,
                   a.notes,a.follow_up,a.letter,j.title,j.company,j.location,j.url,j.score
            FROM applications a JOIN jobs j ON j.id=a.job_id
            ORDER BY CASE a.status
                WHEN 'draft' THEN 0 WHEN 'interview' THEN 1 WHEN 'offer' THEN 2
                WHEN 'applied' THEN 3 ELSE 4 END, a.updated_at DESC
            LIMIT 500""")]


@router.get("/applications/pipeline")
def pipeline():
    return get_pipeline()


@router.post("/applications/prepare", status_code=201)
def prepare(body: ApplicationPreparation):
    with main.connection() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (body.job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Oferta nie istnieje")
        current = db.execute("SELECT * FROM applications WHERE job_id=?", (body.job_id,)).fetchone()
        if current:
            # Do not reset an already submitted/interviewing application!
            return {"created": False, "id": current["id"], "status": current["status"]}
        now = main.current_utc()
        letter = letter_for(job, main.profile_dict())
        cur = db.execute(
            "INSERT INTO applications(job_id,status,created_at,notes,letter,updated_at) VALUES (?,?,?,?,?,?)",
            (body.job_id, "draft", now, "", letter, now))
        db.execute("UPDATE jobs SET status='saved' WHERE id=?", (body.job_id,))
        db.execute(
            "INSERT INTO application_events(application_id,stage,event,created_at) VALUES (?,?,?,?)",
            (cur.lastrowid, "draft", "Przygotowano szkic — nie wysłano zgłoszenia", now))
        db.commit()
        return {"created": True, "id": cur.lastrowid, "status": "draft"}


@router.patch("/applications/pipeline/{app_id}")
def update_application(app_id: int, body: ApplicationUpdate):
    with main.connection() as db:
        existing = db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Aplikacja nie istnieje")
        now = main.current_utc()
        db.execute("""
            UPDATE applications SET status=?,notes=?,follow_up=?,letter=?,updated_at=?
            WHERE id=?""", (body.status, body.notes, body.follow_up.isoformat() if body.follow_up else None,
                            body.letter, now, app_id))
        if existing["status"] != body.status:
            message = {
                "draft": "Wrócono do szkicu (nie wysłano automatycznie)",
                "applied": "Użytkownik potwierdził samodzielne wysłanie aplikacji",
                "interview": "Zaplanowano rozmowę rekrutacyjną",
                "offer": "Otrzymano ofertę zatrudnienia",
                "rejected": "Aplikacja odrzucona",
                "withdrawn": "Wycofano aplikację",
            }[body.status]
            db.execute(
                "INSERT INTO application_events(application_id,stage,event,created_at) VALUES (?,?,?,?)",
                (app_id, body.status, message, now))
        db.execute("UPDATE jobs SET status=? WHERE id=?",
                   ("applied" if body.status in {"applied","interview","offer","rejected"} else "saved", existing["job_id"]))
        db.commit()
    return {"ok": True}


@router.get("/applications/pipeline/{app_id}/events")
def application_events(app_id: int):
    with main.connection() as db:
        if db.execute("SELECT 1 FROM applications WHERE id=?", (app_id,)).fetchone() is None:
            raise HTTPException(404, "Aplikacja nie istnieje")
        return [dict(r) for r in db.execute(
            "SELECT stage,event,created_at FROM application_events WHERE application_id=? ORDER BY id DESC",
            (app_id,))]


@router.delete("/applications/pipeline/{app_id}")
def delete_application(app_id: int):
    with main.connection() as db:
        row = db.execute("SELECT job_id FROM applications WHERE id=?", (app_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Aplikacja nie istnieje")
        db.execute("DELETE FROM application_events WHERE application_id=?", (app_id,))
        db.execute("DELETE FROM applications WHERE id=?", (app_id,))
        db.execute("UPDATE jobs SET status='saved' WHERE id=? AND status='applied'", (row["job_id"],))
        db.commit()
    return {"ok": True}


def csv_cell(value):
    """Prevent formula injection in Excel-compatible CSV exports."""
    text = str(value if value is not None else "")
    return "'" + text if re.match(r"^\s*[=+@\-\t\r]", text) else text


@router.get("/applications/export.csv")
def export_applications():
    columns = ["company", "title", "location", "status", "created_at", "updated_at",
               "follow_up", "notes", "url", "score"]
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in get_pipeline():
        writer.writerow([csv_cell(row[column]) for column in columns])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="jobpilot-applications.csv"',
                             "Cache-Control": "no-store"})


@router.post("/profile/cv/pdf")
async def extract_cv(request: Request):
    if "application/pdf" not in request.headers.get("content-type", "").lower():
        raise HTTPException(415, "Prześlij plik PDF")
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_PDF_BYTES:
        raise HTTPException(413, "Maksymalny rozmiar pliku PDF: 2 MB")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(413, "Maksymalny rozmiar pliku PDF: 2 MB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Nieprawidłowy plik PDF")
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("encrypted")
        if not 1 <= len(reader.pages) <= 12:
            raise ValueError("pages")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        raise HTTPException(422, "Nie można odczytać PDF (limit 12 stron, bez hasła)")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()[:20000]
    if len(text) < 30:
        raise HTTPException(422, "Brak tekstu — skanowane CV wymaga OCR")
    # Just return extracted text for review: no raw document stored or sent to model.
    return {"text": text, "pages": len(reader.pages), "saved": False}
