import os
import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://127.0.0.1:8000")
st.set_page_config(page_title="AI Internship Manager", page_icon="🎓", layout="wide")


def call(method, path, **kw):
    headers = {"Authorization": f"Bearer {st.session_state.token}"} if "token" in st.session_state else {}
    try:
        r = requests.request(method, API + path, headers=headers, timeout=60, **kw)
    except requests.ConnectionError:
        st.error("Backend not running. Start it with: uvicorn app.main:app --reload")
        st.stop()
    if r.status_code >= 400:
        st.error(r.json().get("detail", r.text))
        return None
    return r.json()


# ---------------- Login / Register ----------------
def auth_page():
    st.title("🎓 AI Internship Manager")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        email = st.text_input("Email", key="le")
        pw = st.text_input("Password", type="password", key="lp")
        if st.button("Login"):
            d = call("POST", "/auth/login", json={"email": email, "password": pw})
            if d:
                st.session_state.token, st.session_state.user = d["token"], d["user"]
                st.rerun()
    with t2:
        role = st.selectbox("I am a", ["student", "mentor", "admin"])
        name = st.text_input("Name")
        email = st.text_input("Email", key="re")
        pw = st.text_input("Password (min 6)", type="password", key="rp")
        extra = st.text_input("University" if role == "student" else "Company") if role != "admin" else ""
        if st.button("Create account"):
            body = {"name": name, "email": email, "password": pw, "role": role}
            if role == "student":
                body["university"] = extra
            elif role == "mentor":
                body["company"] = extra
            d = call("POST", "/auth/register", json=body)
            if d:
                st.session_state.token, st.session_state.user = d["token"], d["user"]
                st.rerun()


# ---------------- Student ----------------
def student_pages(page):
    if page == "Profile & Resume":
        st.header("Profile & Resume")
        me = call("GET", "/me")
        st.write(f"**Skills:** {me['skills'] or 'none yet'}")
        f = st.file_uploader("Upload resume (PDF or TXT)", type=["pdf", "txt"])
        if f and st.button("Extract skills with AI"):
            d = call("POST", "/me/resume", files={"file": (f.name, f.getvalue())})
            if d:
                st.success("Skills found: " + ", ".join(d["skills"]))
        edited = st.text_input("Edit skills (comma-separated)", me["skills"])
        if st.button("Save skills"):
            if call("PUT", "/me/skills", json={"skills": edited.split(",")}):
                st.success("Saved")
    elif page == "Recommended Internships":
        st.header("Internships ranked for you")
        for r in call("GET", "/recommendations") or []:
            i = r["internship"]
            with st.expander(f"{i['title']} @ {i['company']}: match {r['score']}%"):
                st.write(i["description"])
                st.write(f"✅ Matched: {', '.join(r['matched']) or '-'}")
                st.write(f"❌ Missing: {', '.join(r['missing']) or '-'}")
                if st.button("Apply", key=f"ap{i['id']}"):
                    if call("POST", f"/applications/{i['id']}"):
                        st.success("Applied!")
    elif page == "My Applications":
        st.header("My Applications")
        for row in call("GET", "/applications/mine") or []:
            a, i = row["application"], row["internship"]
            with st.expander(f"{i['title']} @ {i['company']}: {a['status'].upper()}"):
                if a["status"] == "accepted":
                    week = st.number_input("Week", 1, 52, 1, key=f"w{a['id']}")
                    notes = st.text_area("What did you do this week?", key=f"n{a['id']}")
                    if st.button("Submit log", key=f"s{a['id']}"):
                        if call("POST", f"/applications/{a['id']}/logs",
                                json={"week": week, "student_notes": notes}):
                            st.rerun()
                    for l in call("GET", f"/applications/{a['id']}/logs") or []:
                        st.markdown(f"**Week {l['week']}:** {l['student_notes']}")
                        if l["mentor_feedback"]:
                            st.info("Mentor: " + l["mentor_feedback"])
                    for e in call("GET", f"/applications/{a['id']}/evaluations") or []:
                        st.success("AI evaluation: " + e["summary"])


# ---------------- Mentor / Admin ----------------
def mentor_pages(page):
    if page == "Post Internship":
        st.header("Post an internship")
        title = st.text_input("Title")
        company = st.text_input("Company", st.session_state.user.get("company") or "")
        desc = st.text_area("Description")
        skills = st.text_input("Required skills (comma-separated)")
        loc = st.text_input("Location")
        if st.button("Publish"):
            if call("POST", "/internships", json={"title": title, "company": company, "description": desc,
                                                  "required_skills": skills, "location": loc}):
                st.success("Published")
    elif page == "Manage Internships":
        st.header("Internships")
        for i in call("GET", "/internships") or []:
            with st.expander(f"{i['title']} ({'open' if i['is_open'] else 'closed'})"):
                st.write(f"Skills: {i['required_skills']}")
                tab1, tab2 = st.tabs(["Applicants", "AI-ranked candidates"])
                with tab1:
                    for row in call("GET", f"/internships/{i['id']}/applications") or []:
                        a, s = row["application"], row["student"]
                        st.markdown(f"**{s['name']}**: {a['match_score']}% · *{a['status']}* · {s['skills']}")
                        cols = st.columns(4)
                        for col, st_ in zip(cols, ["shortlisted", "accepted", "rejected"]):
                            if col.button(st_.title(), key=f"{a['id']}{st_}"):
                                if call("PATCH", f"/applications/{a['id']}/status", json={"status": st_}):
                                    st.rerun()
                        if a["status"] == "accepted":
                            for l in call("GET", f"/applications/{a['id']}/logs") or []:
                                st.markdown(f"> Week {l['week']}: {l['student_notes']}")
                                fb = st.text_input("Feedback", l["mentor_feedback"] or "", key=f"fb{l['id']}")
                                if st.button("Save feedback", key=f"sf{l['id']}"):
                                    call("PATCH", f"/logs/{l['id']}/feedback", json={"feedback": fb})
                            if st.button("🤖 Generate AI evaluation", key=f"ev{a['id']}"):
                                e = call("POST", f"/applications/{a['id']}/evaluation")
                                if e:
                                    st.success(e["summary"])
                with tab2:
                    df = pd.DataFrame([{"Name": c["student"]["name"], "Score": c["score"],
                                        "Matched": ", ".join(c["matched"]), "Missing": ", ".join(c["missing"])}
                                       for c in call("GET", f"/internships/{i['id']}/candidates") or []])
                    st.dataframe(df, use_container_width=True)
                if i["is_open"] and st.button("Close internship", key=f"c{i['id']}"):
                    call("PATCH", f"/internships/{i['id']}/close")
                    st.rerun()


def analytics_page():
    st.header("Analytics")
    d = call("GET", "/analytics")
    if not d:
        return
    c = st.columns(5)
    for col, (label, key) in zip(c, [("Students", "students"), ("Mentors", "mentors"),
                                     ("Internships", "internships"), ("Applications", "applications"),
                                     ("Avg match %", "avg_match_score")]):
        col.metric(label, d[key])
    if d["status_breakdown"]:
        st.subheader("Applications by status")
        st.bar_chart(pd.Series(d["status_breakdown"]))
    if d["applications_per_internship"]:
        st.subheader("Applications per internship")
        st.bar_chart(pd.Series(d["applications_per_internship"]))


# ---------------- Router ----------------
if "token" not in st.session_state:
    auth_page()
else:
    user = st.session_state.user
    st.sidebar.write(f"👤 **{user['name']}** ({user['role']})")
    pages = {"student": ["Profile & Resume", "Recommended Internships", "My Applications"],
             "mentor": ["Post Internship", "Manage Internships"],
             "admin": ["Analytics", "Post Internship", "Manage Internships"]}[user["role"]]
    page = st.sidebar.radio("Menu", pages)
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()
    if user["role"] == "student":
        student_pages(page)
    elif page == "Analytics":
        analytics_page()
    else:
        mentor_pages(page)
