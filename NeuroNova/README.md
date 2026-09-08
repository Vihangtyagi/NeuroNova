# Neuronova — SIH26003

**AI-Based Cognitive Gaming and Memory Assistance Platform for Elderly
Dementia Patients in the North Eastern Region (NER)**

A real, running Python prototype — not a mockup. SQLite-backed data,
a genuine scikit-learn Random Forest trend-classification engine,
offline text-to-speech, and a Streamlit UI for both the patient and
the caregiver view.

## What's actually working here

- **3 cognitive games** — Memory Match, Pattern Recall, and **Know Your
  Roots** (a reminiscence/recognition game built from real North East
  festivals, dance, attire, food and crafts, curated by the caregiver) —
  every session's score is written to SQLite, with difficulty that
  adapts round-to-round based on the patient's score. "Know Your Roots"
  content is keyed to the patient's **state** (`patients.state`,
  independent of their UI language) so a patient from, say, Nagaland
  who prefers reading in English still only ever sees Nagaland culture
  in the game, never another state's mislabeled as their own. Content
  exists for Assam, Meghalaya and Manipur so far; other states show a
  clear "not enough content yet" message rather than a mismatched
  culture — see [Adding tradition photos](#adding-tradition-photos).
- **`cognitive_ai.py`** — engineers features from a patient's daily
  average game score (least-squares trend slope, recent-vs-earlier
  average, day-to-day volatility) and feeds them into a **scikit-learn
  Random Forest classifier**, trained at startup on simulated patient
  trajectories and validated on a held-out split (accuracy exposed as
  `MODEL_ACCURACY`/`MODEL_INFO` for callers to surface). Classifies
  **Improving / Stable / Declining** with a **Low/Medium/High** risk
  level, a plain-language recommendation, and a confidence score, and
  the same model drives in-game adaptive difficulty. Swappable for
  real logged multi-patient history once enough exists, without
  touching the app code — same input/output contract.
- **Offline voice** (`voice.py`) — uses the `espeak-ng` system binary
  (no internet, no API key) to read reminders, family messages, and
  tradition notes aloud, for low-literacy or low-vision users and
  low-connectivity areas of NER.
- **Caregiver dashboard** — 21-day engagement chart, medicine
  adherence %, per-game breakdown, auto-generated alerts, a downloadable
  PDF report for doctor/PHC visits, and an editable Traditions & Culture
  gallery — switchable across multiple demo patient profiles (Assam /
  Meghalaya / Manipur).
- **PIN login with 2 roles** — Patient, and Caregiver (full dashboard
  access: reminders, family members, traditions, and patient photos).
  PINs are salted and hashed (sha256) before storage, never kept in
  plain text.
- **Offline patient registration and PIN recovery** — a "+ Register a
  new patient" form on the login screen lets a caregiver onboard a new
  patient on the spot: name, village, preferred language, **state**
  (independently — see above), and a PIN they choose themselves (not a
  shared default). A "Forgot PIN?" flow resets a patient's PIN using a
  separate local admin PIN (the caregiver's own recovery credential,
  distinct from any patient's PIN) — no email or SMS, entirely offline
  (default: `999999`, change `DEFAULT_ADMIN_PIN` in `db.py` before a
  real deployment).
- **Reminders** across Medicine, Hydration, Meal, Activity, Appointment,
  Family, and Custom categories.
- **Photo uploads** for the patient, family members, and traditions
  (caregiver-curated); traditions can also ship as git-committed images
  in `photos/traditions/` so they survive redeploys — see
  [Adding tradition photos](#adding-tradition-photos) below.
- **6-language UI toggle** (English, Assamese, Khasi, Bodo, Manipuri/
  Meitei, Mizo) — English and Assamese are solid; the other four are
  AI-assisted drafts pending native-speaker review (flagged in code).
- **SQLite persistence** — reminders, family members, traditions, and
  every game score genuinely persist across restarts (`NeuroNova.db`).

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
on day one). Delete `NeuroNova.db` any time to reseed from scratch.

## Project structure

```
app.py             Entry point — wires up the database and launches frontend.py
frontend.py        Streamlit UI — every screen: patient games + caregiver dashboard
style.css          Dark neon/glassmorphism theme, loaded by frontend.py
db.py              SQLite schema, seed data, migrations, CRUD helpers
cognitive_ai.py    Trend-detection / risk-classification engine
voice.py           Offline text-to-speech wrapper (espeak-ng)
report.py          PDF caregiver report generator (reportlab)
requirements.txt   Python dependencies
packages.txt       System package for Streamlit Cloud (espeak-ng)
photos/            Bundled demo photos + photos/traditions/ (see below)
```

## Adding tradition photos

`photos/uploads/` (caregiver-uploaded patient/family/tradition photos)
and `NeuroNova.db` itself are both gitignored — on Streamlit Cloud the
container filesystem resets on every redeploy or sleep/wake cycle, so
anything written there at runtime is lost. `photos/traditions/` is the
one exception: it's meant to be **git-committed**, like the bundled
demo patient photos already are.

To add a permanent photo for a tradition, name the file after its
slug and drop it in `photos/traditions/`, then commit and push —
`db.py` attaches it automatically on the next app start, no code or
database changes needed. Each tradition is tagged to one **state**
(`traditions.language`, a `STATES` code — see `db.py`), so a patient
sees exactly **3 recognition questions from their own state** in
"Know Your Roots" — e.g. Ratan Bora (Assam) only ever gets the 3 Assam
items, regardless of his UI language.

Scoped to just the 3 demo patients' states — 9 traditions defined in
`DEMO_TRADITIONS`, but only Assam's 3 have a committed photo so far;
Meghalaya's and Manipur's 6 still need theirs added the same way:

```
Assam - Ratan Bora (done)         Meghalaya - Ma Kiimi Lyngdoh       Manipur - L. Ibemhal Singh
  bihu_dance.jpg    ✅               khasi_jainsem.jpg   ⬜               eromba.jpg      ⬜
  gamosa.jpg        ✅               nongkrem_dance.jpg  ⬜               raas_leela.jpg  ⬜
  muga_silk.jpg     ✅               jadoh.jpg           ⬜               phanek.jpg      ⬜
```

To add a new state, add 3 tuples to `DEMO_TRADITIONS` in `db.py`
(name, category, note, state-code from `STATES`), or use the
caregiver dashboard's "+ Add a tradition" form which now has its own
State selector. A patient registered with a state that has no content
yet sees a clear "no traditions for this state yet" message rather
than another state's culture shown as if it were theirs.

Add Mizo/Bodo/generic items back to `DEMO_TRADITIONS` in `db.py` (they
were trimmed since no demo patient uses them yet) once there's a
patient profile in that language to show them off. Adding a new
tradition via the caregiver dashboard's "+ Add a tradition" form also
lets you tag its region/language the same way.

(`.jpg`, `.jpeg`, `.png` all work.) The caregiver dashboard's own
"+ Add a tradition" upload form still works too — use it for a quick
live demo, but treat it as temporary until the photo is committed.

## Where this goes next (beyond this prototype)

- **Package the local deployment** — the app itself makes zero external
  network calls (SQLite storage, `espeak-ng` for offline TTS, no cloud
  AI calls), so it already runs with no internet connection when
  installed locally; today's Streamlit Cloud hosting is a demo
  convenience, not an architectural requirement. For real NER
  deployment this should ship as a local install (tablet/laptop) rather
  than depend on a hosted URL — a true local-first sync layer for
  multi-device/multi-caregiver use is the next step beyond that.
- **Voice *input*, not just output** — `voice.py` only reads text
  aloud today; adding speech-to-text would let low-literacy patients
  navigate by voice instead of tapping.
- Native-speaker review of the Khasi, Bodo, Manipuri and Mizo UI
  translations (currently AI-assisted drafts).
- Replace the synthetic training/seed data with real logged multi-patient
  history once enough longitudinal data exists, and retrain/upgrade the
  Random Forest classifier (or move to a time-series model) on that real
  data instead of simulated trajectories.
- Move from SQLite to a proper multi-tenant backend for real
  multi-caregiver / hospital deployment.
- **Encrypt the SQLite file at rest** (e.g. SQLCipher). PINs are
  already hashed, but the rest of `NeuroNova.db` (names, villages,
  reminders, notes) is still plain SQLite on disk — fine for this
  prototype, not for a real deployment.
