from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str
    salt: str
    role: str = "student"            # student / mentor / admin
    university: Optional[str] = None
    company: Optional[str] = None    # for mentors
    skills: str = ""                 # comma-separated, filled by AI
    resume_path: Optional[str] = None
    resume_text: Optional[str] = None


class Token(SQLModel, table=True):
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Internship(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    company: str
    description: str
    required_skills: str = ""
    location: Optional[str] = None
    is_open: bool = True
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="user.id")
    internship_id: int = Field(foreign_key="internship.id")
    status: str = "applied"          # applied / shortlisted / accepted / rejected
    match_score: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProgressLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id")
    week: int
    student_notes: str
    mentor_feedback: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id")
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
