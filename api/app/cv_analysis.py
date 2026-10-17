"""Transparent, local comparison of CV text with technologies named in a job ad.

An unmentioned technology is not proof that the applicant lacks the skill.
No external AI model is used, and no data is transmitted to job providers.
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from . import main

router = APIRouter(prefix="/api", dependencies=[Depends(main.authenticated)])

# Curated aliases prevent misleading substring matches (e.g., "go" inside "Django").
# This is a keyword inventory, not an exhaustive competency assessment.
SKILLS = (
    ("Python", (r"python",)),
    ("FastAPI", (r"fastapi",)),
    ("REST API", (r"rest\s*api(?:s)?", r"restful",)),
    ("UiPath", (r"uipath",)),
    ("RPA", (r"rpa", r"robotic\s+process\s+automation")),
    ("AI / sztuczna inteligencja", (r"artificial\s+intelligence", r"sztuczn[aey]\s+inteligencj[aeyi]", r"\bai\b")),
    ("Machine Learning", (r"machine\s+learning", r"uczeni[aeu]\s+maszynow(?:e|ego|ym)", r"\bml\b")),
    ("LLM", (r"\bllms?\b", r"large\s+language\s+models?",)),
    ("OpenAI API", (r"openai",)),
    ("Next.js", (r"next(?:\.|\s*)js",)),
    ("React", (r"react(?:\.js)?",)),
    ("TypeScript", (r"typescript",)),
    ("JavaScript", (r"javascript",)),
    ("Node.js", (r"node(?:\.|\s*)js",)),
    ("HTML / CSS", (r"html", r"\bcss\b",)),
    ("SQL", (r"\bsql\b",)),
    ("PostgreSQL", (r"postgres(?:ql)?",)),
    ("MySQL", (r"mysql",)),
    ("MongoDB", (r"mongodb",)),
    ("Redis", (r"redis",)),
    ("Docker", (r"docker",)),
    ("Kubernetes", (r"kubernetes", r"\bk8s\b",)),
    ("Git", (r"\bgit\b",)),
    ("CI/CD", (r"ci\s*/\s*cd", r"continuous\s+integration",)),
    ("GitHub Actions", (r"github\s+actions",)),
    ("Playwright", (r"playwright",)),
    ("Selenium", (r"selenium",)),
    ("Pandas", (r"pandas",)),
    ("NumPy", (r"numpy",)),
    ("PyTorch", (r"pytorch",)),
    ("TensorFlow", (r"tensorflow",)),
    ("scikit-learn", (r"scikit[ -]?learn", r"sklearn",)),
    ("AWS", (r"\baws\b", r"amazon\s+web\s+services",)),
    ("Azure", (r"microsoft\s+azure", r"\bazure\b",)),
    ("Google Cloud", (r"google\s+cloud", r"\bgcp\b",)),
    ("Linux", (r"linux",)),
    ("Celery", (r"celery",)),
    ("Apache Airflow", (r"airflow",)),
    ("Power BI", (r"power\s*bi",)),
    ("Excel", (r"excel",)),
    ("Java", (r"java",)),
    ("C#", (r"c\s*#", r"csharp",)),
    (".NET", (r"\.net\b", r"dotnet",)),
    ("Django", (r"django",)),
    ("Flask", (r"flask",)),
    ("Fastify", (r"fastify",)),
    ("C++", (r"c\s*\+\+",)),
    ("Go", (r"golang", r"\bgo\b")),
    ("Terraform", (r"terraform",)),
    ("ETL", (r"\betl\b",)),
    ("Grafana", (r"grafana",)),
)

COMPILED = tuple((
    label,
    re.compile(r"(?<![\w])(?:" + "|".join(patterns) + r")(?![\w])", flags=re.I),
) for label, patterns in SKILLS)


def evidence(text: str, match: re.Match, limit: int = 165) -> str:
    """A bounded visible quotation of where a technology was mentioned."""
    start = max(0, match.start() - 65)
    end = min(len(text), match.end() + 88)
    value = " ".join(text[start:end].split())
    if len(value) > limit:
        value = value[:limit].rstrip() + "…"
    return ("…" if start else "") + value + ("…" if end < len(text) else "")


def analyze(job: dict, cv_text: str) -> dict:
    job_text = (job.get("title") or "") + "\n" + (job.get("description") or "")
    cv_text = (cv_text or "").strip()
    cv_present = len(cv_text) >= 20
    matched, unconfirmed, mentioned = [], [], []
    # Offsets allow skills to appear in the same order as the job advertisement.
    for label, pattern in COMPILED:
        jm = pattern.search(job_text)
        if not jm:
            continue
        mentioned.append((jm.start(), label, jm))
    for _, label, jm in sorted(mentioned, key=lambda row: row[0]):
        cv_match = next(pattern.search(cv_text) for name, pattern in COMPILED if name == label) if cv_present else None
        item = {"skill": label, "job_evidence": evidence(job_text, jm)}
        if cv_match:
            matched.append({**item, "cv_evidence": evidence(cv_text, cv_match)})
        elif cv_present:
            unconfirmed.append(item)
    total = len(matched) + len(unconfirmed)
    coverage = round(len(matched) / total * 100) if cv_present and total else None
    if not cv_present:
        note = "Dodaj tekst CV w Ustawieniach, aby przeprowadzić porównanie."
    elif total == 0:
        note = "Nie znaleziono rozpoznawanych technologii w tej ofercie. Nie oznacza to braku wymagań."
    else:
        note = "Brak wzmianki w CV nie oznacza, że nie masz danej umiejętności. Wynik nie jest szansą na zatrudnienie."
    return {
        "job_id": job["id"],
        "title": job["title"],
        "company": job["company"],
        "cv_present": cv_present,
        "matched": matched,
        "unconfirmed": unconfirmed,
        "mentioned": [label for _, label, _ in sorted(mentioned, key=lambda row: row[0])],
        "detected_count": len(mentioned),
        "coverage_percent": coverage,
        "note": note,
        "method": "Lokalne wykrywanie wzmianek o technologiach; bez usług AI i bez przesyłania CV do pracodawcy.",
    }


@router.get("/cv-analysis/{job_id:path}")
def job_cv_analysis(job_id: str):
    with main.connection() as db:
        job = db.execute("SELECT id,title,company,description FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404, "Oferta nie istnieje")
        cv = db.execute("SELECT cv_text FROM profile WHERE id=1").fetchone()["cv_text"]
    return analyze(dict(job), cv)
