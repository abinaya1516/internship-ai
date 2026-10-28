"""AI helpers. Uses Claude if ANTHROPIC_API_KEY is set, else rule-based fallbacks."""
import io
import json
import os
import re
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SKILL_BANK = [
    "python", "java", "javascript", "typescript", "c++", "c", "sql", "html", "css",
    "react", "node", "django", "flask", "fastapi", "pandas", "numpy", "scikit-learn",
    "tensorflow", "pytorch", "machine learning", "deep learning", "nlp", "data analysis",
    "data visualization", "excel", "power bi", "tableau", "git", "docker", "aws", "linux",
    "mongodb", "mysql", "postgresql", "rest api", "communication", "teamwork", "leadership",
    "problem solving", "flutter", "android", "figma", "ui/ux", "cybersecurity", "iot",
]


def _ask(prompt: str, max_tokens: int = 800):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception:
        return None


def extract_text(filename: str, data: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    return data.decode("utf-8", errors="ignore").strip()


def extract_skills(text: str) -> list[str]:
    out = _ask(
        "Extract the technical and soft skills from this resume. Respond ONLY with a "
        "JSON array of short lowercase skill strings, no other text.\n\n" + text[:8000]
    )
    if out:
        try:
            m = re.search(r"\[.*\]", out, re.S)
            skills = json.loads(m.group(0))
            return sorted({str(s).strip().lower() for s in skills if str(s).strip()})
        except Exception:
            pass
    low = text.lower()
    return sorted(s for s in SKILL_BANK
                  if re.search(r"(?<![a-z0-9+#])" + re.escape(s) + r"(?![a-z0-9+#])", low))


def summarize_progress(student: str, role: str, logs: list[dict]) -> str:
    lines = "\n".join(
        f"Week {l['week']}: {l['student_notes']} | Mentor: {l['mentor_feedback'] or 'no feedback'}"
        for l in logs)
    out = _ask(
        f"You are an internship evaluator. Intern: {student}. Role: {role}.\n"
        f"Weekly logs:\n{lines}\n\nWrite a concise evaluation (max 150 words): "
        "summary of work, strengths, areas to improve, and an overall rating out of 10.",
        max_tokens=500)
    if out:
        return out.strip()
    fb = sum(1 for l in logs if l["mentor_feedback"])
    return (f"{student} submitted {len(logs)} weekly log(s) for the {role} role; mentor gave "
            f"feedback on {fb}. Latest update: {logs[-1]['student_notes'][:200]}. "
            "(Rule-based summary: add ANTHROPIC_API_KEY for a full AI evaluation.)")
