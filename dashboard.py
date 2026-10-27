"""StudyOS dashboard  ·  run with: streamlit run dashboard.py"""
import csv
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import analytics, models as m, services
from app.database import Base, SessionLocal, engine
from app.seed import seed

st.set_page_config(page_title="StudyOS", page_icon="🎓", layout="wide")
Base.metadata.create_all(engine)
db = SessionLocal()


def pct(x):
    return "–" if x is None else f"{x:.0%}"


def pick_subject(label="Subject"):
    subjects = db.query(m.Subject).order_by(m.Subject.name).all()
    if not subjects:
        st.info("No subjects yet. Add one in **Library**, or load demo data from the sidebar.")
        return None
    return st.selectbox(label, subjects, format_func=lambda s: s.name)


def dashboard():
    st.title("📊 Progress")
    subject = pick_subject()
    if not subject:
        return
    stats = analytics.subject_stats(db, subject.id)
    if not stats:
        st.info("Add topics to this subject in Library.")
        return
    recs = analytics.recommendations(db, limit=3)
    if recs:
        st.success(f"**Recommendation:** {recs[0]['message']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Weak topics", sum(s["weak"] for s in stats))
    c2.metric("Cards due", sum(s["due_cards"] for s in stats))
    known = [s["mastery"] for s in stats if s["mastery"] is not None]
    c3.metric("Average mastery", pct(sum(known) / len(known)) if known else "–")

    fig = go.Figure(go.Bar(
        x=[(s["mastery"] or 0) * 100 for s in stats], y=[s["topic"] for s in stats], orientation="h",
        marker_color=["#e5534b" if s["weak"] else "#2da44e" if s["status"] == "ok" else "#8b949e" for s in stats],
        text=[f"{(s['mastery'] or 0):.0%}" + ("  ← Weak" if s["weak"] else "") for s in stats],
        textposition="outside"))
    fig.update_layout(title=f"{subject.name}: topic mastery", xaxis=dict(range=[0, 115], title="%"),
                      yaxis=dict(autorange="reversed"), height=110 + 60 * len(stats), margin=dict(l=0, r=0, t=50, b=0))
    st.plotly_chart(fig, width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("Forgetting curve")
        topic = st.selectbox("Topic", stats, format_func=lambda s: s["topic"])
        if topic["stability"]:
            days = list(range(0, 31))
            curve = go.Figure(go.Scatter(x=days, y=[math.exp(-d / topic["stability"]) * 100 for d in days], mode="lines"))
            curve.add_scatter(x=[topic["days_since_review"]], y=[topic["retention"] * 100], mode="markers",
                              marker=dict(size=12, color="#e5534b"), name="Today")
            curve.update_layout(xaxis_title="Days since review", yaxis_title="Predicted retention %",
                                yaxis=dict(range=[0, 105]), height=300, showlegend=False, margin=dict(t=10, b=0))
            st.plotly_chart(curve, width="stretch")
        else:
            st.caption("Review some flashcards in this topic to see its curve.")
    with right:
        st.subheader("Study next")
        for i, r in enumerate(recs, 1):
            st.write(f"**{i}.** {r['message']}  \n<small>{r['subject']}</small>", unsafe_allow_html=True)
    df = pd.DataFrame([{
        "Topic": s["topic"], "Mastery": pct(s["mastery"]), "Retention": pct(s["retention"]),
        "Due cards": s["due_cards"], "Hard questions": s["question_difficulty"]["hard"],
        "Status": s["status"], "Priority": round(s["priority"], 2)} for s in stats])
    st.dataframe(df, hide_index=True, width="stretch")


def review():
    st.title("🃏 Review")
    ss = st.session_state
    if "queue" not in ss:
        ss.queue, ss.show = [c.id for c in services.due_cards(db)], False
    if not ss.queue:
        st.success("🎉 Nothing due right now.")
        if st.button("Check again"):
            del ss["queue"]
            st.rerun()
        return
    card = db.get(m.Flashcard, ss.queue[0])
    st.caption(f"{len(ss.queue)} left · {card.topic.subject.name} / {card.topic.name}")
    st.subheader(card.front)
    if not ss.show:
        if st.button("Show answer", type="primary"):
            ss.show = True
            st.rerun()
        return
    st.info(card.back)
    cols = st.columns(4)
    for col, (label, rating) in zip(cols, [("Again", 1), ("Hard", 3), ("Good", 4), ("Easy", 5)]):
        if col.button(label, key=f"r{rating}", width="stretch"):
            services.review_card(db, card, rating)
            ss.queue.pop(0)
            if rating < 3:
                ss.queue.append(card.id)  # see it again this session
            ss.show = False
            st.rerun()


def quiz():
    st.title("📝 Adaptive quiz")
    ss = st.session_state
    subject = pick_subject()
    if not subject:
        return
    topics = db.query(m.Topic).filter_by(subject_id=subject.id).all()
    topic = st.selectbox("Topic", [None] + topics, format_func=lambda t: "All (weighted to weak topics)" if t is None else t.name)
    n = st.slider("Questions", 3, 20, 5)
    if st.button("Generate quiz", type="primary"):
        for qid in ss.get("quiz", []):
            ss.pop(f"ans{qid}", None)
        picked = services.generate_quiz(db, topic.id if topic else None, subject.id, n)
        ss.quiz, ss.result = [q.id for q in picked], None
        if not picked:
            st.warning("No questions yet. Add some in Library.")
    ids = ss.get("quiz", [])
    if not ids:
        return
    questions = [db.get(m.Question, i) for i in ids]
    if not ss.get("result"):
        for q in questions:
            st.radio(q.text, range(len(q.options)), format_func=lambda i, q=q: q.options[i], index=None, key=f"ans{q.id}")
        if st.button("Submit"):
            ss.result = services.submit_quiz(db, [(q.id, ss.get(f"ans{q.id}", -1) if ss.get(f"ans{q.id}") is not None else -1) for q in questions])
            st.rerun()
    else:
        res = ss.result
        st.metric("Score", f"{res['score']} / {res['total']}")
        for q, d in zip(questions, res["details"]):
            st.write(("✅ " if d["correct"] else "❌ ") + q.text)
            if not d["correct"]:
                st.caption(f"Correct: {q.options[q.correct_index]}. {q.explanation or ''}")


def library():
    st.title("📚 Library")
    with st.expander("➕ New subject"):
        name = st.text_input("Subject name")
        if st.button("Create subject") and name.strip():
            db.add(m.Subject(name=name.strip()))
            try:
                db.commit()
                st.rerun()
            except Exception:
                db.rollback()
                st.error("That subject already exists.")
    subject = pick_subject()
    if not subject:
        return
    with st.expander("➕ New topic"):
        tname = st.text_input("Topic name")
        if st.button("Create topic") and tname.strip():
            db.add(m.Topic(subject_id=subject.id, name=tname.strip()))
            db.commit()
            st.rerun()
    topics = db.query(m.Topic).filter_by(subject_id=subject.id).all()
    if not topics:
        return
    topic = st.selectbox("Topic", topics, format_func=lambda t: t.name)
    notes, cards, qs = st.tabs(["Notes", "Flashcards", "Questions"])
    with notes:
        for n in topic.notes:
            with st.expander(n.title):
                st.markdown(n.content)
        title, content = st.text_input("Note title"), st.text_area("Markdown content")
        if st.button("Add note") and title.strip():
            db.add(m.Note(topic_id=topic.id, title=title.strip(), content=content))
            db.commit()
            st.rerun()
    with cards:
        st.dataframe(pd.DataFrame([{"Front": c.front, "Back": c.back, "Next review": c.next_review}
                                   for c in topic.flashcards]), hide_index=True, width="stretch")
        f, b = st.text_input("Front"), st.text_input("Back")
        if st.button("Add card") and f.strip() and b.strip():
            db.add(m.Flashcard(topic_id=topic.id, front=f.strip(), back=b.strip()))
            db.commit()
            st.rerun()
        up = st.file_uploader("Import CSV (front,back)", type="csv")
        if up and st.button("Import cards"):
            st.success(f"Imported {services.import_cards_csv(db, topic.id, up.getvalue().decode('utf-8'))} cards")
    with qs:
        for q in topic.questions:
            st.write(f"• {q.text}  → *{q.options[q.correct_index]}*")
        text = st.text_input("Question")
        opts = [st.text_input(f"Option {i + 1}", key=f"opt{i}") for i in range(4)]
        correct = st.radio("Correct option", [1, 2, 3, 4], horizontal=True)
        if st.button("Add question"):
            clean = [o.strip() for o in opts if o.strip()]
            if text.strip() and len(clean) >= 2 and correct <= len(clean):
                db.add(m.Question(topic_id=topic.id, text=text.strip(), options=clean, correct_index=correct - 1))
                db.commit()
                st.rerun()
            else:
                st.error("Need a question, at least 2 options, and a valid correct option.")


st.sidebar.title("🎓 StudyOS")
page = st.sidebar.radio("Go to", ["Dashboard", "Review", "Quiz", "Library"], label_visibility="collapsed")
st.sidebar.metric("🔥 Streak", f"{analytics.streak(db)} days")
if not db.query(m.Subject).count() and st.sidebar.button("Load demo data"):
    seed(db)
    st.rerun()
try:
    {"Dashboard": dashboard, "Review": review, "Quiz": quiz, "Library": library}[page]()
finally:
    db.close()
