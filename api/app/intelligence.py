"""Interpretable content-based job ranking with explicit like/dislike feedback.

This isn't hiring probability: scores are heuristics combining TF-IDF, user criteria,
and similarity to postings the user explicitly marked useful or irrelevant.
"""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def terms(value):
    return [part.strip().casefold() for part in (value or "").split(",") if part.strip()]


def job_text(job):
    return f"{job['title']} {job['title']} {job.get('description', '')[:3000]}"


def rank(jobs, profile, feedback=None):
    if not jobs:
        return []
    feedback = list(feedback or [])[:300]
    keywords = terms(profile.get("keywords", ""))
    excluded = terms(profile.get("excluded", ""))
    reference = ((profile.get("cv_text") or "") + " " + " ".join(keywords * 3)).strip()
    corpus = [reference or "Python developer"] + [job_text(job) for job in jobs]
    corpus += [job_text(item) for item in feedback]
    similarities = [0.0] * len(jobs)
    feedback_similarities = None
    try:
        matrix = TfidfVectorizer(
            ngram_range=(1, 2), max_features=10000, sublinear_tf=True,
            strip_accents="unicode"
        ).fit_transform(corpus)
        similarities = cosine_similarity(matrix[0:1], matrix[1:len(jobs)+1]).ravel()
        if feedback:
            feedback_similarities = cosine_similarity(
                matrix[1:len(jobs)+1], matrix[len(jobs)+1:])
    except ValueError:
        pass

    output = []
    for index, job in enumerate(jobs):
        text = (job["title"] + " " + job.get("description", "")).casefold()
        matched = [term for term in keywords if term in text]
        matched_ratio = len(matched) / max(1, len(keywords))
        location = (profile.get("location") or "").strip().casefold()
        location_matches = bool(location and (location in job.get("location", "").casefold()
                                 or location in text[:400]))
        remote = bool(job.get("remote", False))
        semantic = float(similarities[index])
        base = round(65 * min(1, semantic * 2.4) + 25 * matched_ratio +
                     10 * (remote or location_matches))
        benefit = 0
        if feedback_similarities is not None:
            positive = [float(feedback_similarities[index][j]) for j, item in enumerate(feedback)
                        if item.get("opinion") == 1 and item.get("id") != job.get("id")]
            negative = [float(feedback_similarities[index][j]) for j, item in enumerate(feedback)
                        if item.get("opinion") == -1 and item.get("id") != job.get("id")]
            # Explicit opinions, without treating ignored jobs as implicit feedback.
            benefit = round(22 * max(positive, default=0) - 27 * max(negative, default=0))
        blocked = any(term in text for term in excluded) or (profile.get("remote_only") and not remote)
        if (not keywords and not profile.get("cv_text")) or blocked:
            score = 0
        else:
            score = max(0, min(100, base + benefit))
        reasons = []
        if matched:
            reasons.append("Pasuje: " + ", ".join(matched[:4]))
        else:
            reasons.append("Podobieństwo treści oferty do profilu")
        if benefit >= 3:
            reasons.append("zbliżona do polubionych ofert")
        elif benefit <= -3:
            reasons.append("zbliżona do niechcianych ofert")
        if blocked:
            reasons = ["Odrzucona przez filtr preferencji"]
        output.append({**job, "score": score, "reason": "; ".join(reasons)})
    return output
