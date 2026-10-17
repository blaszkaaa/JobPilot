"""Explicit learning feedback, sync history and notification inbox."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import intelligence, main

router = APIRouter(prefix="/api", dependencies=[Depends(main.authenticated)])


class FeedbackChange(BaseModel):
    opinion: Literal["like", "dislike", "clear"]


def examples(db=None):
    """Training examples are job snapshots selected by explicit user feedback."""
    if db is None:
        with main.connection() as conn:
            return examples(conn)
    return [dict(row) for row in db.execute("""
        SELECT j.id,j.title,j.description,f.opinion
        FROM job_feedback f JOIN jobs j ON j.id=f.job_id
        ORDER BY f.updated_at DESC LIMIT 300
    """)]


def recompute(db=None, profile=None):
    if db is None:
        with main.connection() as conn:
            recompute(conn, profile)
            conn.commit()
            return
    profile = profile or dict(db.execute("SELECT * FROM profile WHERE id=1").fetchone())
    listings = [dict(row) for row in db.execute("SELECT * FROM jobs")]
    results = intelligence.rank(listings, profile, examples(db))
    db.executemany("UPDATE jobs SET score=?,reason=? WHERE id=?",
                   [(item["score"], item["reason"], item["id"]) for item in results])


@router.post("/jobs/{job_id:path}/feedback")
def change_feedback(job_id: str, body: FeedbackChange):
    value = {"like": 1, "dislike": -1, "clear": 0}[body.opinion]
    with main.connection() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise HTTPException(404, "Oferta nie istnieje")
        if value:
            db.execute("""
                INSERT INTO job_feedback(job_id,opinion,updated_at) VALUES (?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET
                  opinion=excluded.opinion,updated_at=excluded.updated_at
            """, (job_id, value, main.current_utc()))
        else:
            db.execute("DELETE FROM job_feedback WHERE job_id=?", (job_id,))
        recompute(db)
        db.commit()
    return {"ok": True, "opinion": value}


@router.get("/scans")
def scans():
    with main.connection() as db:
        return [dict(r) for r in db.execute("""
            SELECT id,scanned_at,fetched,new_matches,errors
            FROM scan_history ORDER BY id DESC LIMIT 25
        """)]


@router.patch("/notifications/{notification_id}/read")
def mark_read(notification_id: int):
    with main.connection() as db:
        row = db.execute("SELECT id FROM notifications WHERE id=?", (notification_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Nie znaleziono powiadomienia")
        db.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=?",
                   (main.current_utc(), notification_id))
        db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read():
    with main.connection() as db:
        changed = db.execute("UPDATE notifications SET read_at=? WHERE read_at IS NULL",
                             (main.current_utc(),)).rowcount
        db.commit()
    return {"ok": True, "changed": changed}
