import re
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from . import ai
from .database import get_session, init_db
from .matching import match
from .models import Application, Evaluation, Internship, ProgressLog, User
from .security import create_token, current_user, hash_password, new_salt, require

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Internship Manager", lifespan=lifespan)


def public(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "university": u.university, "company": u.company, "skills": u.skills}


# ---------------- Auth ----------------
class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"
    university: Optional[str] = None
    company: Optional[str] = None


class LoginIn(BaseModel):
    email: str
    password: str


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/auth/register")
def register(data: RegisterIn, session: Session = Depends(get_session)):
    if data.role not in ("student", "mentor", "admin"):
        raise HTTPException(400, "Invalid role")
    if not re.match(r"[^@]+@[^@]+\.[^@]+", data.email):
        raise HTTPException(400, "Invalid email")
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if session.exec(select(User).where(User.email == data.email.lower())).first():
        raise HTTPException(400, "Email already registered")
    salt = new_salt()
    user = User(name=data.name, email=data.email.lower(), role=data.role,
                university=data.university, company=data.company,
                salt=salt, password_hash=hash_password(data.password, salt))
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"token": create_token(session, user.id), "user": public(user)}


@app.post("/auth/login")
def login(data: LoginIn, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == data.email.lower())).first()
    if not user or user.password_hash != hash_password(data.password, user.salt):
        raise HTTPException(401, "Wrong email or password")
    return {"token": create_token(session, user.id), "user": public(user)}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return public(user)


# ---------------- Resume + skills ----------------
@app.post("/me/resume")
async def upload_resume(file: UploadFile = File(...), user: User = Depends(require("student")),
                        session: Session = Depends(get_session)):
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(400, "File too large (max 5 MB)")
    if not file.filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(400, "Only PDF or TXT resumes are supported")
    try:
        text = ai.extract_text(file.filename, data)
    except Exception:
        raise HTTPException(400, "Could not read this file")
    if not text:
        raise HTTPException(400, "No text found in the resume (scanned image?)")
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    path.write_bytes(data)
    skills = ai.extract_skills(text)
    user.resume_path, user.resume_text = str(path), text[:20000]
    user.skills = ",".join(skills)
    session.add(user)
    session.commit()
    return {"skills": skills}


class SkillsIn(BaseModel):
    skills: list[str]


@app.put("/me/skills")
def set_skills(data: SkillsIn, user: User = Depends(require("student")),
               session: Session = Depends(get_session)):
    user.skills = ",".join(sorted({s.strip().lower() for s in data.skills if s.strip()}))
    session.add(user)
    session.commit()
    return {"skills": user.skills}


# ---------------- Internships ----------------
class InternshipIn(BaseModel):
    title: str
    company: Optional[str] = None
    description: str
    required_skills: str = ""
    location: Optional[str] = None


@app.post("/internships")
def create_internship(data: InternshipIn, user: User = Depends(require("mentor", "admin")),
                      session: Session = Depends(get_session)):
    company = data.company or user.company
    if not company:
        raise HTTPException(400, "Company name required")
    item = Internship(**{**data.model_dump(), "company": company}, owner_id=user.id)
    item.required_skills = ",".join(s.strip().lower() for s in item.required_skills.split(",") if s.strip())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@app.get("/internships")
def list_internships(user: User = Depends(current_user), session: Session = Depends(get_session)):
    q = select(Internship)
    if user.role == "student":
        q = q.where(Internship.is_open == True)  # noqa: E712
    elif user.role == "mentor":
        q = q.where(Internship.owner_id == user.id)
    return session.exec(q).all()


@app.patch("/internships/{iid}/close")
def close_internship(iid: int, user: User = Depends(require("mentor", "admin")),
                     session: Session = Depends(get_session)):
    item = session.get(Internship, iid)
    if not item or (user.role == "mentor" and item.owner_id != user.id):
        raise HTTPException(404, "Internship not found")
    item.is_open = False
    session.add(item)
    session.commit()
    return item


def _text(i: Internship) -> str:
    return f"{i.title} {i.description} {i.required_skills}"


@app.get("/recommendations")
def recommendations(user: User = Depends(require("student")),
                    session: Session = Depends(get_session)):
    out = []
    for i in session.exec(select(Internship).where(Internship.is_open == True)).all():  # noqa: E712
        m = match(user.skills, user.resume_text or "", i.required_skills, _text(i))
        out.append({"internship": i, **m})
    return sorted(out, key=lambda x: x["score"], reverse=True)


@app.get("/internships/{iid}/candidates")
def rank_candidates(iid: int, user: User = Depends(require("mentor", "admin")),
                    session: Session = Depends(get_session)):
    i = session.get(Internship, iid)
    if not i or (user.role == "mentor" and i.owner_id != user.id):
        raise HTTPException(404, "Internship not found")
    out = []
    for s in session.exec(select(User).where(User.role == "student")).all():
        m = match(s.skills, s.resume_text or "", i.required_skills, _text(i))
        out.append({"student": public(s), **m})
    return sorted(out, key=lambda x: x["score"], reverse=True)


# ---------------- Applications ----------------
@app.post("/applications/{iid}")
def apply(iid: int, user: User = Depends(require("student")),
          session: Session = Depends(get_session)):
    i = session.get(Internship, iid)
    if not i or not i.is_open:
        raise HTTPException(404, "Internship not found or closed")
    if session.exec(select(Application).where(Application.student_id == user.id,
                                              Application.internship_id == iid)).first():
        raise HTTPException(400, "Already applied")
    m = match(user.skills, user.resume_text or "", i.required_skills, _text(i))
    a = Application(student_id=user.id, internship_id=iid, match_score=m["score"])
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@app.get("/applications/mine")
def my_applications(user: User = Depends(require("student")),
                    session: Session = Depends(get_session)):
    rows = session.exec(select(Application, Internship).join(
        Internship, Internship.id == Application.internship_id)
        .where(Application.student_id == user.id)).all()
    return [{"application": a, "internship": i} for a, i in rows]


@app.get("/internships/{iid}/applications")
def internship_applications(iid: int, user: User = Depends(require("mentor", "admin")),
                            session: Session = Depends(get_session)):
    i = session.get(Internship, iid)
    if not i or (user.role == "mentor" and i.owner_id != user.id):
        raise HTTPException(404, "Internship not found")
    rows = session.exec(select(Application, User).join(User, User.id == Application.student_id)
                        .where(Application.internship_id == iid)
                        .order_by(Application.match_score.desc())).all()
    return [{"application": a, "student": public(s)} for a, s in rows]


TRANSITIONS = {"applied": {"shortlisted", "rejected"},
               "shortlisted": {"accepted", "rejected"}}


class StatusIn(BaseModel):
    status: str


def _owned_application(aid: int, user: User, session: Session) -> Application:
    a = session.get(Application, aid)
    if not a:
        raise HTTPException(404, "Application not found")
    i = session.get(Internship, a.internship_id)
    if user.role == "mentor" and i.owner_id != user.id:
        raise HTTPException(403, "Not your internship")
    if user.role == "student" and a.student_id != user.id:
        raise HTTPException(403, "Not your application")
    return a


@app.patch("/applications/{aid}/status")
def set_status(aid: int, data: StatusIn, user: User = Depends(require("mentor", "admin")),
               session: Session = Depends(get_session)):
    a = _owned_application(aid, user, session)
    if data.status not in TRANSITIONS.get(a.status, set()):
        raise HTTPException(400, f"Cannot move from '{a.status}' to '{data.status}'")
    a.status = data.status
    session.add(a)
    session.commit()
    return a


# ---------------- Progress tracking ----------------
class LogIn(BaseModel):
    week: int
    student_notes: str


class FeedbackIn(BaseModel):
    feedback: str


@app.post("/applications/{aid}/logs")
def add_log(aid: int, data: LogIn, user: User = Depends(require("student")),
            session: Session = Depends(get_session)):
    a = _owned_application(aid, user, session)
    if a.status != "accepted":
        raise HTTPException(400, "Logs allowed only for accepted internships")
    log = ProgressLog(application_id=aid, **data.model_dump())
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@app.get("/applications/{aid}/logs")
def get_logs(aid: int, user: User = Depends(current_user),
             session: Session = Depends(get_session)):
    _owned_application(aid, user, session)
    return session.exec(select(ProgressLog).where(ProgressLog.application_id == aid)
                        .order_by(ProgressLog.week)).all()


@app.patch("/logs/{lid}/feedback")
def give_feedback(lid: int, data: FeedbackIn, user: User = Depends(require("mentor", "admin")),
                  session: Session = Depends(get_session)):
    log = session.get(ProgressLog, lid)
    if not log:
        raise HTTPException(404, "Log not found")
    _owned_application(log.application_id, user, session)
    log.mentor_feedback = data.feedback
    session.add(log)
    session.commit()
    return log


@app.post("/applications/{aid}/evaluation")
def evaluate(aid: int, user: User = Depends(require("mentor", "admin")),
             session: Session = Depends(get_session)):
    a = _owned_application(aid, user, session)
    logs = session.exec(select(ProgressLog).where(ProgressLog.application_id == aid)
                        .order_by(ProgressLog.week)).all()
    if not logs:
        raise HTTPException(400, "No progress logs yet")
    student = session.get(User, a.student_id)
    internship = session.get(Internship, a.internship_id)
    summary = ai.summarize_progress(student.name, internship.title, [l.model_dump() for l in logs])
    ev = Evaluation(application_id=aid, summary=summary)
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev


@app.get("/applications/{aid}/evaluations")
def get_evaluations(aid: int, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    _owned_application(aid, user, session)
    return session.exec(select(Evaluation).where(Evaluation.application_id == aid)).all()


# ---------------- Analytics ----------------
@app.get("/analytics")
def analytics(user: User = Depends(require("admin")), session: Session = Depends(get_session)):
    apps = session.exec(select(Application)).all()
    internships = session.exec(select(Internship)).all()
    titles = {i.id: i.title for i in internships}
    scores = [a.match_score for a in apps if a.match_score is not None]
    return {
        "students": len(session.exec(select(User).where(User.role == "student")).all()),
        "mentors": len(session.exec(select(User).where(User.role == "mentor")).all()),
        "internships": len(internships),
        "open_internships": sum(i.is_open for i in internships),
        "applications": len(apps),
        "status_breakdown": dict(Counter(a.status for a in apps)),
        "applications_per_internship": dict(Counter(titles[a.internship_id] for a in apps)),
        "avg_match_score": round(sum(scores) / len(scores), 1) if scores else 0,
    }
