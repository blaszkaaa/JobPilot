"""JobPilot API: single-owner portfolio MVP; no unauthorised job-site scraping."""
import asyncio
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DB_PATH = Path(os.getenv("DATABASE_PATH", "/data/jobpilot.sqlite3"))
ADMIN_EMAIL = os.getenv("JOBPILOT_ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("JOBPILOT_ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("JOBPILOT_SESSION_SECRET", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
SYNC_INTERVAL = max(300, int(os.getenv("SYNC_INTERVAL_SECONDS", "1800")))
GREENHOUSE_BOARDS = [x.strip() for x in os.getenv("GREENHOUSE_BOARDS", "").split(",") if x.strip()]
LEVER_SITES = [x.strip() for x in os.getenv("LEVER_SITES", "").split(",") if x.strip()]
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "pl").lower()
ADZUNA_QUERY = os.getenv("ADZUNA_QUERY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
sync_lock = asyncio.Lock()
login_attempts = {}
last_sync = {"at": None, "error": None, "count": 0}

class Login(BaseModel):
    email: str
    password: str

class Profile(BaseModel):
    full_name: str = Field(default="", max_length=120)
    location: str = Field(default="Polska", max_length=120)
    keywords: str = Field(default="Python, FastAPI, automatyzacja, AI", max_length=500)
    excluded: str = Field(default="", max_length=300)
    cv_text: str = Field(default="", max_length=20000)
    remote_only: bool = False
    min_score: int = Field(default=60, ge=0, le=100)

class StatusChange(BaseModel):
    status: str

def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=15)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id=1), full_name TEXT NOT NULL,
            location TEXT NOT NULL, keywords TEXT NOT NULL, excluded TEXT NOT NULL,
            cv_text TEXT NOT NULL, remote_only INTEGER NOT NULL, min_score INTEGER NOT NULL)""")
        db.execute("""INSERT OR IGNORE INTO profile VALUES
            (1,'','Polska','Python, FastAPI, automatyzacja, AI','','',0,60)""")
        db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL,
            location TEXT NOT NULL, remote INTEGER NOT NULL, description TEXT NOT NULL,
            url TEXT NOT NULL, source TEXT NOT NULL, posted_at TEXT,
            score INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
            discovered_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new')""")
        db.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, message TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL, created_at TEXT NOT NULL)""")
        db.commit()

    from .features import initialize_features
    from .sources import initialize_sources
    initialize_features()
    initialize_sources()

def profile_dict():
    with connection() as db:
        return dict(db.execute("SELECT * FROM profile WHERE id=1").fetchone())

def current_utc():
    return datetime.now(timezone.utc).isoformat()

def split_terms(text):
    return [t.strip().lower() for t in text.split(",") if t.strip()]

def plain(text):
    text = re.sub(r"<[^>]*>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()[:12000]

def safe_url(url):
    parsed = urlparse(url or "")
    return url if parsed.scheme == "https" and parsed.netloc else ""

def signed_session():
    until = int(time.time()) + 7 * 86400
    payload = f"owner:{until}"
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def authenticated(request: Request):
    token = request.cookies.get("jp_session", "")
    pieces = token.split(":")
    if len(pieces) != 3 or pieces[0] != "owner":
        raise HTTPException(401, "Zaloguj się do JobPilot")
    payload = ":".join(pieces[:2])
    sig = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, pieces[2]) or not pieces[1].isdigit() or int(pieces[1]) < time.time():
        raise HTTPException(401, "Sesja wygasła")
    return True

def rank(jobs, profile, feedback=None):
    from .intelligence import rank as calculate_rank
    return calculate_rank(jobs, profile, feedback)


def greenhouse_job(item, board):
    location = (item.get("location") or {}).get("name") or "Nie podano"
    body = (item.get("content") or "")
    return {
        "id": f"greenhouse:{board}:{item['id']}", "title": item.get("title") or "Oferta pracy",
        "company": board.replace("-", " ").title(), "location": location,
        "remote": bool(re.search(r"remote|zdaln", location + " " + item.get("title", ""), re.I)),
        "description": plain(body), "url": safe_url(item.get("absolute_url")),
        "source": "Greenhouse", "posted_at": item.get("updated_at")
    }

def lever_job(item, site):
    location = ((item.get("categories") or {}).get("location")) or "Nie podano"
    mode = item.get("workplaceType") or ""
    return {
        "id": f"lever:{site}:{item['id']}", "title": item.get("text") or "Oferta pracy",
        "company": site.replace("-", " ").title(), "location": location,
        "remote": "remote" in mode.lower() or bool(re.search(r"remote|zdaln", location, re.I)),
        "description": plain(item.get("descriptionPlain") or item.get("description") or ""),
        "url": safe_url(item.get("hostedUrl") or item.get("applyUrl")),
        "source": "Lever", "posted_at": item.get("createdAt")
    }

async def fetch_jobs(client):
    combined = []
    errors = []
    try:
        res = await client.get("https://www.arbeitnow.com/api/job-board-api", params={"page": 1})
        res.raise_for_status()
        for item in res.json().get("data", [])[:100]:
            combined.append({
                "id": f"arbeitnow:{item['slug']}", "title": item.get("title") or "Oferta pracy",
                "company": item.get("company_name") or "Nieznana firma",
                "location": item.get("location") or "Nie podano",
                "remote": bool(item.get("remote")), "description": plain(item.get("description")),
                "url": safe_url(item.get("url")), "source": "Arbeitnow",
                "posted_at": str(item.get("created_at") or "")
            })
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        errors.append("Arbeitnow: " + type(exc).__name__)
    from .sources import resolve_boards
    for board in resolve_boards("greenhouse"):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", board):
            continue
        try:
            res = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"})
            res.raise_for_status()
            combined += [greenhouse_job(j, board) for j in res.json().get("jobs", [])[:150]]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"Greenhouse/{board}: {type(exc).__name__}")
    for site in resolve_boards("lever"):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", site):
            continue
        try:
            res = await client.get(f"https://api.lever.co/v0/postings/{site}", params={"mode": "json"})
            res.raise_for_status()
            combined += [lever_job(j, site) for j in res.json()[:150]]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"Lever/{site}: {type(exc).__name__}")
    if ADZUNA_APP_ID and ADZUNA_APP_KEY and re.fullmatch(r"[a-z]{2}", ADZUNA_COUNTRY):
        # Saved searches add precise, user-managed queries. Fallback preserves v0.1 behaviour.
        from .features import active_watches
        watches, configured = active_watches()
        if not configured:
            profile = profile_dict()
            terms = split_terms(profile["keywords"])
            city = profile["location"].split(",")[0].strip()
            watches = [{"query": ADZUNA_QUERY or (terms[0] if terms else "python"),
                        "location": "" if city.lower() in {"polska", "poland", "remote"} else city}]
        for watch in watches:
            try:
                res = await client.get(
                    f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1",
                    params={"app_id": ADZUNA_APP_ID, "app_key": ADZUNA_APP_KEY,
                            "results_per_page": 50, "what": watch["query"],
                            "where": watch["location"]}
                )
                res.raise_for_status()
                for item in res.json().get("results", []):
                    combined.append({
                        "id": f"adzuna:{ADZUNA_COUNTRY}:{item['id']}",
                        "title": item.get("title") or "Oferta pracy",
                        "company": (item.get("company") or {}).get("display_name") or "Nieznana firma",
                        "location": (item.get("location") or {}).get("display_name") or "Nie podano",
                        "remote": bool(re.search(r"remote|zdaln", (item.get("title") or "") + " " + (item.get("description") or ""), re.I)),
                        "description": plain(item.get("description") or ""),
                        "url": safe_url(item.get("redirect_url")),
                        "source": "Adzuna",
                        "posted_at": item.get("created") or ""
                    })
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                errors.append("Adzuna: " + type(exc).__name__)
    return [j for j in combined if j["url"]], errors

async def send_telegram(client, message):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": message[:3500]})
    except httpx.HTTPError:
        pass

async def refresh():
    if sync_lock.locked():
        return {"busy": True, **last_sync}
    async with sync_lock:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            records, errors = await fetch_jobs(client)
            from .learning import examples
            ranked = rank(records, profile_dict(), examples())
            now = current_utc()
            new_matches = []
            with connection() as db:
                for job in ranked:
                    exists = db.execute("SELECT id FROM jobs WHERE id=?", (job["id"],)).fetchone()
                    db.execute("""INSERT INTO jobs
                        (id,title,company,location,remote,description,url,source,posted_at,score,reason,discovered_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,company=excluded.company,location=excluded.location,
                        remote=excluded.remote,description=excluded.description,url=excluded.url,
                        posted_at=excluded.posted_at,score=excluded.score,reason=excluded.reason""",
                        (job["id"], job["title"], job["company"], job["location"], int(job["remote"]),
                         job["description"], job["url"], job["source"], job["posted_at"],
                         job["score"], job["reason"], now))
                    if not exists and job["score"] >= profile_dict()["min_score"]:
                        new_matches.append(job)
                for job in new_matches[:10]:
                    db.execute("INSERT INTO notifications(job_id,message,created_at) VALUES (?,?,?)",
                               (job["id"], f'Nowa oferta: {job["title"]} • {job["company"]} ({job["score"]}%)', now))
                db.commit()
            if new_matches:
                top = sorted(new_matches, key=lambda j: j["score"], reverse=True)[:3]
                msg = "JobPilot: nowe dopasowane oferty\n" + "\n".join(
                    f'• {j["title"]} — {j["company"]} ({j["score"]}%)\n{j["url"]}' for j in top
                )
                await send_telegram(client, msg)
            from .features import queue_due_followups
            reminders = queue_due_followups()
            if reminders:
                await send_telegram(client, "JobPilot — kontakt z rekruterem\n" + "\n".join(
                    reminder["text"] + "\n" + reminder["url"] for reminder in reminders[:5]))
            with connection() as db:
                db.execute(
                    "INSERT INTO scan_history(scanned_at,fetched,new_matches,errors) VALUES (?,?,?,?)",
                    (now, len(ranked), len(new_matches), "; ".join(errors) or None))
                db.execute("DELETE FROM scan_history WHERE id NOT IN (SELECT id FROM scan_history ORDER BY id DESC LIMIT 500)")
                db.commit()
            last_sync.update(at=now, error="; ".join(errors) if errors else None, count=len(ranked))
            return {"new_matches": len(new_matches), **last_sync}

async def periodic_sync():
    await asyncio.sleep(8)
    while True:
        try:
            await refresh()
        except Exception as exc:
            last_sync.update(error=f"Sync: {type(exc).__name__}")
        await asyncio.sleep(SYNC_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not ADMIN_EMAIL or len(ADMIN_PASSWORD) < 12 or len(SESSION_SECRET) < 32:
        raise RuntimeError("Configure JOBPILOT_ADMIN_EMAIL, JOBPILOT_ADMIN_PASSWORD (12+) and JOBPILOT_SESSION_SECRET (32+).")
    initialize()
    task = asyncio.create_task(periodic_sync())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="JobPilot", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    address = request.client.host if request.client else "unknown"
    now = time.time()
    login_attempts[address] = [t for t in login_attempts.get(address, []) if now - t < 600]
    if len(login_attempts[address]) >= 12:
        raise HTTPException(429, "Za dużo prób. Spróbuj za 10 minut.")
    valid = hmac.compare_digest(body.email.strip().lower(), ADMIN_EMAIL) and hmac.compare_digest(body.password, ADMIN_PASSWORD)
    if not valid:
        login_attempts[address].append(now)
        raise HTTPException(401, "Nieprawidłowe dane logowania")
    login_attempts.pop(address, None)
    response.set_cookie("jp_session", signed_session(), max_age=604800, httponly=True,
                        secure=COOKIE_SECURE, samesite="lax", path="/")
    return {"ok": True}

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("jp_session", path="/")
    return {"ok": True}

@app.get("/api/me")
def me(_=Depends(authenticated)):
    return {"email": ADMIN_EMAIL, "name": profile_dict()["full_name"] or "Administrator"}

@app.get("/api/profile")
def get_profile(_=Depends(authenticated)):
    profile = profile_dict()
    profile.pop("id", None)
    profile["remote_only"] = bool(profile["remote_only"])
    return profile

@app.put("/api/profile")
def set_profile(body: Profile, _=Depends(authenticated)):
    with connection() as db:
        db.execute("""UPDATE profile SET full_name=?,location=?,keywords=?,excluded=?,
            cv_text=?,remote_only=?,min_score=? WHERE id=1""",
            (body.full_name,body.location,body.keywords,body.excluded,body.cv_text,
             int(body.remote_only),body.min_score))
        from .learning import recompute
        recompute(db, body.model_dump())
        db.commit()
    return {"ok": True}

@app.get("/api/stats")
def stats(_=Depends(authenticated)):
    from .sources import resolve_boards
    with connection() as db:
        total = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        matched = db.execute("SELECT count(*) FROM jobs WHERE score>=? AND status != 'ignored'",
                             (profile_dict()["min_score"],)).fetchone()[0]
        saved = db.execute("SELECT count(*) FROM jobs WHERE status='saved'").fetchone()[0]
        applied = db.execute("SELECT count(*) FROM applications WHERE status IN ('applied','interview','offer','rejected')").fetchone()[0]
        likes = db.execute("SELECT count(*) FROM job_feedback WHERE opinion=1").fetchone()[0]
        dislikes = db.execute("SELECT count(*) FROM job_feedback WHERE opinion=-1").fetchone()[0]
        unread = db.execute("SELECT count(*) FROM notifications WHERE read_at IS NULL").fetchone()[0]
    return {"total": total, "matched": matched, "saved": saved, "applied": applied,
            "last_sync": last_sync, "likes": likes, "dislikes": dislikes,
            "unread": unread, "telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
            "sources": ["Arbeitnow"] + (["Greenhouse"] if resolve_boards("greenhouse") else []) +
            (["Lever"] if resolve_boards("lever") else []) +
            (["Adzuna"] if ADZUNA_APP_ID and ADZUNA_APP_KEY else [])}

@app.get("/api/jobs")
def list_jobs(q: str = "", status: str = "all", remote: bool = False, _=Depends(authenticated)):
    sql = """SELECT jobs.*, COALESCE(
        (SELECT opinion FROM job_feedback f WHERE f.job_id = jobs.id),0
    ) AS feedback FROM jobs WHERE 1=1"""
    args = []
    if status != "all":
        if status not in {"new", "saved", "ignored", "applied"}:
            raise HTTPException(400, "Nieznany status")
        sql += " AND status=?"
        args.append(status)
    if remote:
        sql += " AND remote=1"
    if q.strip():
        sql += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
        args += [f"%{q.strip()}%"] * 3
    sql += " ORDER BY score DESC, discovered_at DESC LIMIT 300"
    with connection() as db:
        jobs = [dict(r) for r in db.execute(sql, args)]
    for j in jobs:
        j["remote"] = bool(j["remote"])
    return jobs

@app.post("/api/jobs/refresh")
async def sync_jobs(_=Depends(authenticated)):
    return await refresh()

@app.patch("/api/jobs/{job_id:path}/status")
def change_status(job_id: str, body: StatusChange, _=Depends(authenticated)):
    if body.status not in {"new", "saved", "ignored", "applied"}:
        raise HTTPException(400, "Nieznany status")
    with connection() as db:
        row = db.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Oferta nie istnieje")
        db.execute("UPDATE jobs SET status=? WHERE id=?", (body.status, job_id))
        if body.status == "applied":
            db.execute("INSERT OR IGNORE INTO applications(job_id,status,created_at,updated_at) VALUES (?,?,?,?)",
                       (job_id, "applied", current_utc(), current_utc()))
        db.commit()
    return {"ok": True}

@app.get("/api/notifications")
def notifications(_=Depends(authenticated)):
    with connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 60")]

@app.get("/api/applications")
def applications(_=Depends(authenticated)):
    with connection() as db:
        return [dict(r) for r in db.execute("""SELECT a.id,a.status,a.created_at,j.title,j.company,j.url
            FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.created_at DESC LIMIT 100""")]

@app.post("/api/jobs/{job_id:path}/draft")
def draft(job_id: str, _=Depends(authenticated)):
    with connection() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Oferta nie istnieje")
    profile = profile_dict()
    name = profile["full_name"] or "[Imię i nazwisko]"
    skills = profile["keywords"] or "[Twoje umiejętności]"
    # Intentionally a clearly-labelled template, never invented qualifications.
    letter = (f"Dzień dobry,\n\nChciałbym aplikować na stanowisko {row['title']} "
              f"w {row['company']}.\n\nMoje doświadczenie i umiejętności obejmują: {skills}. "
              "Chętnie opowiem, jak mogę je wykorzystać w Państwa zespole.\n\n"
              f"Z poważaniem,\n{name}")
    return {"draft": letter, "type": "template", "sent": False}

# The optional search rules, application pipeline and PDF import are in a separate module.
from .features import router as workspace_router
app.include_router(workspace_router)
from .learning import router as learning_router
app.include_router(learning_router)
from .sources import router as sources_router
app.include_router(sources_router)
