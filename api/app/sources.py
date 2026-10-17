"""Manage public ATS job boards and manually entered listings.

Requests to external URLs are NOT made for manually entered job links; the
registered board adapter builds HTTPS endpoints on trusted provider hosts.
"""
import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main

router = APIRouter(prefix="/api", dependencies=[Depends(main.authenticated)])
SLUG = re.compile(r"^[a-zA-Z0-9_-]{2,80}$")


class BoardCreate(BaseModel):
    provider: Literal["greenhouse", "lever"]
    slug: str = Field(min_length=2, max_length=80)
    label: str = Field(default="", max_length=100)
    enabled: bool = True


class BoardUpdate(BaseModel):
    enabled: bool


class ManualJob(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    company: str = Field(min_length=2, max_length=120)
    location: str = Field(default="Nie podano", max_length=120)
    description: str = Field(min_length=30, max_length=12000)
    url: str = Field(min_length=12, max_length=2000)
    remote: bool = False


def initialize_sources():
    with main.connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS board_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL CHECK(provider IN ('greenhouse','lever')),
            slug TEXT NOT NULL, label TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, UNIQUE(provider,slug)
        )""")
        db.commit()


def resolve_boards(provider: str):
    """Merge environmental boards with enabled user-managed sources, deduplicated."""
    initial = main.GREENHOUSE_BOARDS if provider == "greenhouse" else main.LEVER_SITES
    with main.connection() as db:
        selected = [r["slug"] for r in db.execute(
            "SELECT slug FROM board_sources WHERE provider=? AND enabled=1 ORDER BY id", (provider,))]
    seen = set()
    result = []
    for slug in initial + selected:
        key = slug.lower()
        if SLUG.fullmatch(slug) and key not in seen:
            result.append(slug)
            seen.add(key)
    return result[:20]


@router.get("/sources")
def list_sources():
    with main.connection() as db:
        managed = [dict(row) for row in db.execute(
            "SELECT id,provider,slug,label,enabled,created_at FROM board_sources ORDER BY id DESC")]
    for row in managed:
        row["enabled"] = bool(row["enabled"])
        row["managed"] = True
    manual = []
    for provider, slugs in [("greenhouse", main.GREENHOUSE_BOARDS), ("lever", main.LEVER_SITES)]:
        for slug in slugs:
            if SLUG.fullmatch(slug) and not any(
                r["provider"] == provider and r["slug"].lower() == slug.lower() for r in managed
            ):
                manual.append({"id": None, "provider": provider, "slug": slug,
                               "label": slug, "enabled": True, "managed": False, "created_at": None})
    return {"boards": managed + manual,
            "providers": {"arbeitnow": True, "adzuna": bool(main.ADZUNA_APP_ID and main.ADZUNA_APP_KEY)},
            "limits": {"max_managed": 20, "max_per_provider_fetch": 20}}


@router.post("/sources", status_code=201)
def add_source(body: BoardCreate):
    slug = body.slug.strip().lower()
    if not SLUG.fullmatch(slug):
        raise HTTPException(422, "Identyfikator musi zawierać 2–80 liter, cyfr, _ lub -")
    label = body.label.strip() or slug
    with main.connection() as db:
        if db.execute("SELECT count(*) FROM board_sources").fetchone()[0] >= 20:
            raise HTTPException(400, "Limit 20 źródeł firm")
        if db.execute("SELECT 1 FROM board_sources WHERE provider=? AND lower(slug)=?", (body.provider, slug)).fetchone():
            raise HTTPException(409, "Ta firma została już dodana")
        cursor = db.execute(
            "INSERT INTO board_sources(provider,slug,label,enabled,created_at) VALUES (?,?,?,?,?)",
            (body.provider, slug, label, int(body.enabled), main.current_utc()))
        db.commit()
    return {"id": cursor.lastrowid, "provider": body.provider, "slug": slug,
            "label": label, "enabled": body.enabled, "managed": True}


@router.patch("/sources/{source_id}")
def toggle_source(source_id: int, body: BoardUpdate):
    with main.connection() as db:
        cursor = db.execute("UPDATE board_sources SET enabled=? WHERE id=?",
                            (int(body.enabled), source_id))
        db.commit()
    if not cursor.rowcount:
        raise HTTPException(404, "Nie znaleziono źródła")
    return {"ok": True}


@router.delete("/sources/{source_id}")
def delete_source(source_id: int):
    with main.connection() as db:
        cursor = db.execute("DELETE FROM board_sources WHERE id=?", (source_id,))
        db.commit()
    if not cursor.rowcount:
        raise HTTPException(404, "Nie znaleziono źródła")
    return {"ok": True}


def verified_job_link(url: str):
    """No network request; only an HTTPS web address can be saved/opened."""
    raw = url.strip()
    try:
        u = urlsplit(raw)
        if (u.scheme.lower() != "https" or not u.hostname
                or u.username or u.password or len(u.hostname) > 253
                or any(char.isspace() for char in raw)
                or u.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("invalid")
        # Require a public DNS name; do not allow IP literals or local names.
        if "." not in u.hostname or u.hostname.endswith((".local", ".internal", ".test")):
            raise ValueError("invalid")
        try:
            ipaddress.ip_address(u.hostname)
        except ValueError:
            pass
        else:
            raise ValueError("invalid")
        return raw
    except ValueError:
        raise HTTPException(422, "Podaj poprawny publiczny adres HTTPS ogłoszenia")


@router.post("/jobs/manual", status_code=201)
def add_manual_job(body: ManualJob):
    url = verified_job_link(body.url)
    normalized = url.split("#", 1)[0].rstrip("/")
    job_id = "manual:" + hashlib.sha256(normalized.encode()).hexdigest()[:32]
    now = main.current_utc()
    job = {
        "id": job_id, "title": body.title.strip(), "company": body.company.strip(),
        "location": body.location.strip() or "Nie podano", "remote": body.remote,
        "description": main.plain(body.description), "url": url,
        "source": "Manual", "posted_at": "", "status": "new", "discovered_at": now
    }
    from .learning import examples
    ranked = main.rank([job], main.profile_dict(), examples())[0]
    with main.connection() as db:
        if db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise HTTPException(409, "Ta oferta została już dodana")
        db.execute("""INSERT INTO jobs
            (id,title,company,location,remote,description,url,source,
             posted_at,score,reason,discovered_at,status)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job_id, job["title"], job["company"], job["location"], int(job["remote"]),
             job["description"], job["url"], "Manual", "", ranked["score"],
             ranked["reason"], now, "new"))
        db.commit()
    return {"ok": True, "job_id": job_id, "score": ranked["score"]}
