# Smriti Sathi — SIH26003

**AI-Based Cognitive Gaming and Memory Assistance Platform for Elderly
Dementia Patients in the North Eastern Region (NER)**

A real, running Python prototype — not a mockup. SQLite-backed data,
a genuine linear-regression "AI" trend-detection engine, offline
text-to-speech, and a Streamlit UI for both the patient and the
caregiver/ASHA-worker view.

## What's actually working here

- **3 cognitive games** (Memory Match, Pattern Recall, "Who Is This?"
  family recognition) — every session's score is written to SQLite.
- **`cognitive_ai.py`** — fits a least-squares trend line (numpy) over a
  patient's daily average game score, flags **Improving / Stable /
  Declining** with a **Low/Medium/High** risk level, and produces a
  plain-language recommendation. Transparent and swappable for a
  heavier model later (e.g. LSTM over multi-modal signals) without
  touching the app code — same input/output contract.
- **Offline voice** (`voice.py`) — uses the `espeak-ng` system binary
  (no internet, no API key) to read reminders and family messages
  aloud, for low-literacy or low-vision users and low-connectivity
  areas of NER.
- **Caregiver dashboard** — 21-day engagement chart, medicine
  adherence %, per-game breakdown, and auto-generated alerts, switchable
  across multiple demo patient profiles (Assam / Meghalaya / Manipur).
- **Bilingual UI toggle** (English / Assamese) as a proof-of-concept for
  the multi-language requirement across NER states.
- **SQLite persistence** — reminders, family members, and every game
  score genuinely persist across restarts (`smriti.db`).

## Run it

```bash
pip install -r requirements.txt

# Optional but recommended — enables the offline voice feature:
#   Ubuntu/Debian: sudo apt-get install espeak-ng
#   macOS:         brew install espeak-ng
#   Windows:       install eSpeak NG from https://github.com/espeak-ng/espeak-ng/releases
# The app works fine without it; voice buttons just show text instead.

streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501).

The database seeds itself automatically on first run with 3 demo
patients, their families, today's reminders, and 21 days of synthetic
game-history (deliberately shaped so one patient trends down, one is
stable, one trends up — so the AI dashboard has something real to show
on day one). Delete `smriti.db` any time to reseed from scratch.

## Project structure

```
app.py            Streamlit UI — patient games + caregiver dashboard
db.py             SQLite schema, seed data, CRUD helpers
cognitive_ai.py   Trend-detection / risk-classification engine
voice.py          Offline text-to-speech wrapper (espeak-ng)
requirements.txt  Python dependencies
```

## Where this goes next (beyond this prototype)

- Replace the synthetic seed history with real logged sessions.
- Swap the linear-trend model for a proper time-series model once
  enough longitudinal data exists per patient.
- Add speech-*to*-text so patients can navigate by voice, not just
  listen (useful for low-literacy users).
- Extend the language dictionary to Khasi, Bodo, Manipuri and Mizo.
- Move from SQLite to a proper multi-tenant backend for real ASHA
  worker / hospital deployment.
