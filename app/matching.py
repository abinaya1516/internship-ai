from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def parse_skills(s: str) -> set[str]:
    return {x.strip().lower() for x in (s or "").split(",") if x.strip()}


def match(student_skills: str, student_text: str, required: str, internship_text: str) -> dict:
    req, have = parse_skills(required), parse_skills(student_skills)
    overlap = len(req & have) / len(req) if req else 0.0
    cos = 0.0
    profile = f"{student_skills} {student_text or ''}".strip()
    if profile and internship_text.strip():
        try:
            m = TfidfVectorizer(stop_words="english").fit_transform([profile, internship_text])
            cos = float(cosine_similarity(m[0], m[1])[0][0])
        except ValueError:
            pass
    score = round(100 * (0.6 * overlap + 0.4 * cos), 1)
    return {"score": score, "matched": sorted(req & have), "missing": sorted(req - have)}
