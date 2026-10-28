# 🎓 AI-Powered Internship Management System

FastAPI + SQLModel (SQLite) + Streamlit + Claude API (optional).

## Features
- Roles: student / mentor (company) / admin, token auth, hashed passwords
- Resume upload (PDF/TXT) → AI skill extraction
- AI matching: 60% skill overlap + 40% TF-IDF text similarity → 0–100 score
- Application workflow: applied → shortlisted → accepted/rejected
- Weekly progress logs, mentor feedback, AI-generated evaluations
- Admin analytics dashboard

## Run
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optionally add ANTHROPIC_API_KEY
uvicorn app.main:app --reload            # terminal 1  -> http://127.0.0.1:8000/docs
streamlit run frontend/app.py            # terminal 2  -> http://localhost:8501
pytest -q                                # run tests
```
Without an API key, skill extraction uses a keyword bank and evaluations use a rule-based summary.

## Demo flow
1. Register a **mentor** → Post Internship (skills: `python,pandas,docker`)
2. Register a **student** → upload resume → Recommended Internships → Apply
3. Mentor → Manage Internships → Shortlist → Accept
4. Student → My Applications → submit weekly log
5. Mentor → feedback → Generate AI evaluation
6. Register an **admin** → Analytics
