# 🎓 StudyOS: Personal Learning Management System

**Notion + Anki + progress analytics.** Organize study material as
`Subject → Topic → Notes → Flashcards → Quizzes → Progress`, then let Python tell you *what to study next*.

```
DATABASE MANAGEMENT
Normalization      89%
SQL                76%
Transactions       62%
Indexing           45%  ← Weak
ER Modeling        81%

Focus on Indexing next (mastery 45%, retention 18%, 3 cards due).
```
<!-- Add screenshots: docs/dashboard.png, docs/review.png -->

## Features
- **Library:** subjects, topics, Markdown notes, flashcards (with CSV import), multiple-choice questions
- **Spaced repetition:** SM-2 scheduling, a daily due queue and full review history
- **Adaptive quizzes:** weak topics and historically hard questions are sampled more often
- **Analytics:** topic mastery, weak-topic detection, forgetting-curve retention, question difficulty, ranked recommendations, study streak
- **Two interfaces:** REST API (FastAPI) and interactive dashboard (Streamlit)

## Quick start
```bash
pip install -r requirements.txt
python -m app.seed                # demo data (optional)
streamlit run dashboard.py        # dashboard
uvicorn app.main:app --reload     # API docs at http://127.0.0.1:8000/docs
pytest -q                         # 24 tests
```

## Architecture
```
app/
  models.py      SQLAlchemy models (Subject, Topic, Note, Flashcard, ReviewLog, Question, QuizAttempt, QuestionResult)
  sm2.py         pure SM-2 function
  analytics.py   mastery / retention / difficulty / priority (the "brain")
  services.py    review, adaptive quiz generation, quiz grading, CSV import
  routers/       generic CRUD factory + review / quiz / analytics endpoints
  seed.py        demo data with simulated study history
dashboard.py     Streamlit UI (calls services + analytics directly)
```
Every review and quiz answer is stored as its own row, never overwritten, so all analytics are derived from history.

## The algorithms
**SM-2 (scheduling).** After a review rated 0-5: a rating below 3 resets the card to a 1-day interval. Otherwise the interval goes 1 → 6 → `interval × ease`. Ease is adjusted by `0.1 − (5−q)(0.08 + (5−q)·0.02)` and floored at 1.3.

**Mastery.** `0.6 × quiz accuracy + 0.4 × flashcard accuracy`, where each accuracy is recency-weighted with a 14-day half-life (`weight = 0.5^(age/14)`). Mastery below 60% is flagged **weak**.

**Retention (Ebbinghaus).** `R = e^(−t/S)`, where `t` is days since a card's last review and `S` is its stability (its current SM-2 interval). Topic retention is the mean over reviewed cards.

**Question difficulty.** Success rate above 80% is *easy*, 50-80% is *medium*, below 50% is *hard*. Quiz sampling weight is `(0.5 + 2·failure_rate) × (0.5 + (1 − topic_mastery))`.

**Recommendations.** `priority = 0.5(1 − mastery) + 0.3(1 − retention) + 0.2·overdue_ratio`. The highest-priority topic becomes "Focus on X next".

## API overview
| Endpoint | Purpose |
|---|---|
| `/subjects /topics /notes /flashcards /questions` | CRUD (`?parent_id=` filters by parent) |
| `GET /review/due` · `POST /review/{card_id}` | due queue · submit rating 0-5 |
| `POST /quizzes/generate` · `POST /quizzes/submit` | adaptive quiz (no answer key) · grading |
| `GET /analytics/subject/{id}` · `/recommendations` · `/streak` | progress data |

## Deploy
Streamlit Community Cloud: point it at `dashboard.py`. It uses SQLite, so data resets on redeploy; switch `DATABASE_URL` in `app/database.py` to Postgres for persistence.

## Ideas for next steps
Alembic migrations, user accounts, Anki `.apkg` import, Markdown note search, per-question timing analytics.
