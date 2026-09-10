"""
db.py — SQLite data layer for Neuronova
Handles schema creation, demo-data seeding, and all CRUD helpers
used by the Streamlit UI (frontend.py) and the AI engine (cognitive_ai.py).
"""

import sqlite3
import os
import random
import re
import secrets
import hashlib
import uuid
from datetime import datetime, timedelta
from cryptography.fernet import Fernet, InvalidToken

DB_PATH = os.path.join(os.path.dirname(__file__), "NeuroNova.db")
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")

# Local-only key for encrypting sensitive free-text fields at rest (patient
# name/village, family notes, reminder tasks) -- generated once on first run
# and never committed (see .gitignore). This is field-level encryption done
# in the app layer rather than whole-database encryption (e.g. SQLCipher),
# because SQLCipher's Python bindings don't ship a wheel for every Python
# version -- this approach needs nothing beyond the pure-Python
# `cryptography` package, so it works everywhere without extra install steps.
_KEY_PATH = os.path.join(os.path.dirname(__file__), "db_secret.key")


def _load_or_create_key():
    if os.path.exists(_KEY_PATH):
        with open(_KEY_PATH, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(_KEY_PATH, "wb") as f:
        f.write(key)
    return key


_FERNET = Fernet(_load_or_create_key())


def _enc(text):
    """Encrypt a plain-text field before it's written to SQLite. None/empty
    values pass through untouched -- nothing sensitive to protect there."""
    if not text:
        return text
    return _FERNET.encrypt(text.encode()).decode()


def _dec(token):
    """Decrypt a field read back from SQLite. Falls back to returning the
    raw value on failure (e.g. empty/None, or a pre-encryption legacy row)
    rather than raising, since a display glitch is far better than a crash."""
    if not token:
        return token
    try:
        return _FERNET.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return token

# Languages supported for a patient's preferred language, keyed by the code
# stored in patients.language. Native names included for display purposes.
# This is purely UI translation -- it does NOT determine which culture the
# "Know Your Roots" game shows (see STATES / patients.state below). A patient
# can read the app in English and still be culturally from Nagaland.
LANGUAGES = {
    "en": "English",
    "as": "Assamese (অসমীয়া)",
    "kha": "Khasi",
    "brx": "Bodo (बड़ो)",
    "mni": "Manipuri / Meitei (মৈতৈলোন্)",
    "lus": "Mizo (Mizo ṭawng)",
}

# The 8 North Eastern Region states, keyed by the code stored in
# patients.state and traditions.language -- this is what actually drives
# "Know Your Roots" content, independent of the UI language above. Content
# only exists for assam/meghalaya/manipur so far (see DEMO_TRADITIONS);
# see get_traditions_for_state() for what a patient from any other state
# sees until content is added for them.
STATES = {
    "assam": "Assam",
    "arunachal_pradesh": "Arunachal Pradesh",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "sikkim": "Sikkim",
    "tripura": "Tripura",
}


# Demo default for the caregiver's own admin credential, used to reset a
# patient's PIN -- entirely local (no email/SMS), for the offline "forgot
# PIN" flow. Change this before a real deployment.
DEFAULT_ADMIN_PIN = "999999"


def _new_salt():
    return secrets.token_hex(8)


def _hash_pin(pin, salt):
    """PINs are never stored in plain text -- sha256(salt + pin), salt kept
    alongside. Pure local computation, no network involved, so this works
    identically offline."""
    return hashlib.sha256((salt + pin).encode()).hexdigest()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(force_reseed=False):
    """Create tables if missing, and seed demo data on first run."""
    first_run = not os.path.exists(DB_PATH)
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            village TEXT,
            language TEXT DEFAULT 'en',
            state TEXT DEFAULT '',
            pin TEXT DEFAULT '1234',
            pin_salt TEXT DEFAULT '',
            photo_path TEXT
        );

        CREATE TABLE IF NOT EXISTS app_admin (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            pin_hash TEXT NOT NULL,
            pin_salt TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            relation TEXT NOT NULL,
            initials TEXT,
            last_contact TEXT,
            note TEXT,
            photo_path TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            time_str TEXT NOT NULL,
            task TEXT NOT NULL,
            type TEXT,
            icon TEXT,
            done INTEGER DEFAULT 0,
            reminder_date TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS game_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            game_type TEXT NOT NULL,
            score REAL NOT NULL,
            max_score REAL NOT NULL,
            played_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS traditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            note TEXT,
            photo_path TEXT,
            language TEXT DEFAULT ''
        );
        """
    )
    conn.commit()

    existing_cols = [row[1] for row in cur.execute("PRAGMA table_info(patients)")]
    if "pin" not in existing_cols:
        cur.execute("ALTER TABLE patients ADD COLUMN pin TEXT DEFAULT '1234'")
        conn.commit()
    if "photo_path" not in existing_cols:
        cur.execute("ALTER TABLE patients ADD COLUMN photo_path TEXT")
        conn.commit()
    if "pin_salt" not in existing_cols:
        cur.execute("ALTER TABLE patients ADD COLUMN pin_salt TEXT DEFAULT ''")
        conn.commit()
    if "state" not in existing_cols:
        cur.execute("ALTER TABLE patients ADD COLUMN state TEXT DEFAULT ''")
        conn.commit()

    family_cols = [row[1] for row in cur.execute("PRAGMA table_info(family_members)")]
    if "photo_path" not in family_cols:
        cur.execute("ALTER TABLE family_members ADD COLUMN photo_path TEXT")
        conn.commit()

    tradition_cols = [row[1] for row in cur.execute("PRAGMA table_info(traditions)")]
    if "language" not in tradition_cols:
        cur.execute("ALTER TABLE traditions ADD COLUMN language TEXT DEFAULT ''")
        conn.commit()

    os.makedirs(PHOTOS_DIR, exist_ok=True)

    if first_run or force_reseed:
        _seed_demo_data(conn)
    else:
        _seed_traditions_if_empty(conn)

    _migrate_family_match_scores(conn)
    _migrate_tradition_languages(conn)
    _migrate_patient_pins_to_hashed(conn)
    _migrate_patient_states(conn)
    _seed_admin_pin_if_missing(conn)
    _attach_bundled_tradition_photos(conn)
    _top_up_game_scores(conn)

    conn.close()


# (name, category, note, state) -- state is the STATES code this item
# belongs to ("" = generic/pan-NER, shown to every patient as fallback
# filler). Exactly 3 curated items per state so a patient's own cultural
# background (e.g. from Assam) gets exactly 3 recognition questions of
# their own heritage in "Know Your Roots" -- independent of whatever UI
# language they've chosen to read the app in.
#
# Scoped to just 3 of the 8 NER states (Assam, Meghalaya, Manipur) for now
# -- add more states here (and matching photos in photos/traditions/) once
# there's a patient profile from that state to show them off.
DEMO_TRADITIONS = [
    # Assam
    ("Bihu Dance", "Dance", "The traditional harvest-festival dance of Assam, danced to the dhol and pepa.", "assam"),
    ("Gamosa", "Attire", "A woven Assamese cloth of respect and honour, gifted on special occasions.", "assam"),
    ("Muga Silk", "Attire", "Assam's golden silk, woven for generations and worn on festive occasions.", "assam"),
    # Meghalaya
    ("Khasi Jainsem", "Attire", "The traditional draped dress worn by Khasi women of Meghalaya.", "meghalaya"),
    ("Nongkrem Dance", "Dance", "A Khasi thanksgiving dance performed at the Ka Shad Nongkrem harvest festival in Smit, Meghalaya.", "meghalaya"),
    ("Jadoh", "Food", "A traditional Khasi rice dish of Meghalaya, cooked with meat and often coloured with pig's blood.", "meghalaya"),
    # Manipur
    ("Eromba", "Food", "A traditional Manipuri dish of boiled vegetables mashed with fermented fish.", "manipur"),
    ("Raas Leela", "Dance", "A classical Manipuri dance depicting the life of Krishna and Radha, performed in ornate costume.", "manipur"),
    ("Phanek", "Attire", "The traditional wraparound skirt worn by Meitei women of Manipur.", "manipur"),
]


def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _attach_bundled_tradition_photos(conn):
    """Pick up permanent tradition photos from photos/traditions/ -- unlike
    photos/uploads/ (gitignored, wiped whenever Streamlit Cloud restarts the
    app container), this folder is meant to be git-committed, so photos
    placed here survive every redeploy/sleep-wake cycle. Drop a file named
    after the tradition's slug (e.g. 'bihu_dance.jpg' for 'Bihu Dance') and
    it's attached automatically on the next app start -- no DB edit needed."""
    bundled_dir = os.path.join(PHOTOS_DIR, "traditions")
    if not os.path.isdir(bundled_dir):
        return

    available = {}
    for fname in os.listdir(bundled_dir):
        stem, ext = os.path.splitext(fname)
        if ext.lower() in (".jpg", ".jpeg", ".png"):
            available[_slugify(stem)] = fname

    cur = conn.cursor()
    rows = cur.execute("SELECT id, name, photo_path FROM traditions").fetchall()
    changed = False
    for row in rows:
        fname = available.get(_slugify(row["name"]))
        if not fname:
            continue
        bundled_path = f"photos/traditions/{fname}"
        if row["photo_path"] != bundled_path:
            cur.execute("UPDATE traditions SET photo_path = ? WHERE id = ?", (bundled_path, row["id"]))
            changed = True
    if changed:
        conn.commit()


def _seed_traditions_if_empty(conn):
    """Backfill the demo traditions list if the table is empty, without
    touching anything else -- lets an already-seeded database (added on an
    earlier version, before this table existed) pick up starter content on
    the next run instead of showing an empty 'Know Your Roots' game."""
    cur = conn.cursor()
    count = cur.execute("SELECT COUNT(*) FROM traditions").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO traditions (name, category, note, photo_path, language) VALUES (?, ?, ?, ?, ?)",
            [(name, category, note, None, language) for name, category, note, language in DEMO_TRADITIONS],
        )
        conn.commit()


def _migrate_tradition_languages(conn):
    """One-time (repeatable) migration for a DB seeded before per-state
    tagging existed: syncs the `language` (really: state) tag on
    already-seeded traditions to match DEMO_TRADITIONS -- this covers both
    backfilling an empty tag and retagging an old language-code value
    (e.g. 'as') to the current state-code value ('assam') -- and adds any
    new DEMO_TRADITIONS entries the DB doesn't have yet. Only ever touches
    rows matched by name to a known DEMO_TRADITIONS entry, so a caregiver's
    own custom-named traditions are never touched."""
    cur = conn.cursor()
    by_name = {name: (category, note, language) for name, category, note, language in DEMO_TRADITIONS}

    existing = cur.execute("SELECT id, name, language FROM traditions").fetchall()
    existing_names = {row["name"] for row in existing}
    changed = False

    for row in existing:
        if row["name"] in by_name:
            _, _, language = by_name[row["name"]]
            if language and row["language"] != language:
                cur.execute("UPDATE traditions SET language = ? WHERE id = ?", (language, row["id"]))
                changed = True

    for name, (category, note, language) in by_name.items():
        if name not in existing_names:
            cur.execute(
                "INSERT INTO traditions (name, category, note, photo_path, language) VALUES (?, ?, ?, ?, ?)",
                (name, category, note, None, language),
            )
            changed = True

    if changed:
        conn.commit()


def _migrate_patient_pins_to_hashed(conn):
    """One-time (and self-repeating-safe) migration: any patient whose PIN
    is still stored in plain text (pin_salt empty -- true for demo-seeded
    patients using the '1234' column default, and for any DB created before
    hashing existed) gets a random salt and their PIN rehashed in place.
    Pure local computation, runs on every init_db() but only touches rows
    that still need it."""
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, pin FROM patients WHERE pin_salt IS NULL OR pin_salt = ''"
    ).fetchall()
    for row in rows:
        salt = _new_salt()
        cur.execute(
            "UPDATE patients SET pin = ?, pin_salt = ? WHERE id = ?",
            (_hash_pin(row["pin"], salt), salt, row["id"]),
        )
    if rows:
        conn.commit()


# Reasonable one-time default for backfilling patients.state from their
# existing UI language, for patients created before the two fields were
# separated. New registrations set state explicitly and independently.
_LANGUAGE_TO_STATE_DEFAULT = {
    "as": "assam", "kha": "meghalaya", "mni": "manipur",
    "lus": "mizoram", "brx": "assam",
}


def _migrate_patient_states(conn):
    """One-time (repeatable) migration: backfill patients.state from the
    patient's existing language for any row that doesn't have a state yet
    -- lets already-registered patients (including the 3 demo profiles)
    get correct 'Know Your Roots' content without needing to be re-edited
    by hand. New registrations set state directly via the registration
    form, independent of language."""
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, language FROM patients WHERE state IS NULL OR state = ''"
    ).fetchall()
    changed = False
    for row in rows:
        state = _LANGUAGE_TO_STATE_DEFAULT.get(row["language"])
        if state:
            cur.execute("UPDATE patients SET state = ? WHERE id = ?", (state, row["id"]))
            changed = True
    if changed:
        conn.commit()


def _seed_admin_pin_if_missing(conn):
    """Seed the one local caregiver admin PIN used to reset a patient's
    PIN when it's forgotten (see reset_patient_pin) -- offline equivalent
    of a password-reset email, checked entirely against the
    local database."""
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM app_admin WHERE id = 1").fetchone()[0] == 0:
        salt = _new_salt()
        cur.execute(
            "INSERT INTO app_admin (id, pin_hash, pin_salt) VALUES (1, ?, ?)",
            (_hash_pin(DEFAULT_ADMIN_PIN, salt), salt),
        )
        conn.commit()


def _migrate_family_match_scores(conn):
    """One-time migration for a DB seeded before 'Know Your Roots' replaced
    the retired 'Who Is This?' family-photo game: any leftover family_match
    score history is retired and replaced with fresh traditions_match dummy
    scores (same per-patient trend shape and play cadence, new random
    values) so the caregiver trend charts and AI alerts have data for the
    new game instead of a blank/missing row."""
    cur = conn.cursor()
    old_rows = cur.execute(
        "SELECT id, patient_id, played_at, score FROM game_scores "
        "WHERE game_type = 'family_match' ORDER BY patient_id, played_at"
    ).fetchall()
    if not old_rows:
        return

    by_patient = {}
    for r in old_rows:
        by_patient.setdefault(r["patient_id"], []).append(r)

    for pid, rows in by_patient.items():
        scores = [r["score"] for r in rows]
        if len(scores) >= 2:
            xs = list(range(len(scores)))
            mean_x, mean_y = sum(xs) / len(xs), sum(scores) / len(scores)
            denom = sum((x - mean_x) ** 2 for x in xs)
            slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, scores)) / denom if denom else 0.0
        else:
            slope = 0.0
        base = scores[0] if scores else 65

        for i, r in enumerate(rows):
            new_score = max(5, min(100, base + slope * i + random.uniform(-6, 6)))
            cur.execute(
                "INSERT INTO game_scores (patient_id, game_type, score, max_score, played_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, "traditions_match", round(new_score, 1), 100, r["played_at"]),
            )

    cur.execute("DELETE FROM game_scores WHERE game_type = 'family_match'")
    conn.commit()


def _seed_demo_data(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM game_scores")
    cur.execute("DELETE FROM reminders")
    cur.execute("DELETE FROM family_members")
    cur.execute("DELETE FROM patients")
    cur.execute("DELETE FROM traditions")

    patients = [
        ("Ratan Bora", 74, "Sonapur, Assam", "as", "photos/demo_ratan_bora.png"),
        ("Ma Kiimi Lyngdoh", 69, "Mawlai, Meghalaya", "kha", "photos/demo_ma_kiimi_lyngdoh.png"),
        ("L. Ibemhal Singh", 78, "Imphal, Manipur", "mni", "photos/demo_l_ibemhal_singh.png"),
    ]
    cur.executemany(
        "INSERT INTO patients (name, age, village, language, photo_path) VALUES (?, ?, ?, ?, ?)",
        [(_enc(name), age, _enc(village), lang, photo) for name, age, village, lang, photo in patients],
    )
    conn.commit()

    patient_ids = [row[0] for row in cur.execute("SELECT id FROM patients ORDER BY id")]

    family_data = {
        patient_ids[0]: [
            ("Priya Bora", "Daughter", "PB", "Visited 2 days ago", "She calls every evening and loves you very much."),
            ("Anil Bora", "Son", "AB", "Visited last week", "Works in Guwahati, video-calls every Sunday."),
            ("Mina Devi", "Wife", "MD", "Lives with you", "Makes your morning tea every day."),
            ("Rohan Bora", "Grandson", "RB", "Visited 2 days ago", "9 years old, loves your Bihu stories."),
        ],
        patient_ids[1]: [
            ("Banri Lyngdoh", "Daughter", "BL", "Visited today", "Calls every morning from Shillong."),
            ("Kmen Lyngdoh", "Son", "KL", "Visited last month", "Works at a tea estate nearby."),
        ],
        patient_ids[2]: [
            ("Sanjenbam Singh", "Son", "SS", "Visited yesterday", "Lives nearby in Imphal."),
            ("Ibetombi Singh", "Daughter-in-law", "IS", "Visits daily", "Cooks your favourite eromba on Sundays."),
        ],
    }
    for pid, members in family_data.items():
        for name, relation, initials, last, note in members:
            slug = name.lower().replace(".", "").replace(" ", "_")
            photo_path = f"photos/demo_{slug}.png"
            cur.execute(
                "INSERT INTO family_members (patient_id, name, relation, initials, last_contact, note, photo_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, _enc(name), relation, initials, last, _enc(note), photo_path),
            )
    conn.commit()

    _seed_traditions_if_empty(conn)

    today = datetime.now().strftime("%Y-%m-%d")
    reminder_data = {
        patient_ids[0]: [
            ("07:30 AM", "Morning medicine — Blood pressure tablet", "Medicine", "💊", 1),
            ("08:30 AM", "Breakfast with family", "Meal", "🍚", 1),
            ("11:00 AM", "Play today's memory games", "Activity", "🧩", 0),
            ("01:00 PM", "Afternoon medicine — Sugar tablet", "Medicine", "💊", 0),
            ("04:00 PM", "Video call with Anil", "Family", "📞", 0),
            ("08:00 PM", "Evening medicine", "Medicine", "💊", 0),
        ],
        patient_ids[1]: [
            ("08:00 AM", "Morning medicine", "Medicine", "💊", 1),
            ("12:30 PM", "Lunch", "Meal", "🍚", 0),
        ],
        patient_ids[2]: [
            ("07:00 AM", "Morning medicine", "Medicine", "💊", 1),
            ("02:00 PM", "Physiotherapy visit", "Activity", "🧩", 0),
        ],
    }
    for pid, rows in reminder_data.items():
        for time_str, task, rtype, icon, done in rows:
            cur.execute(
                "INSERT INTO reminders (patient_id, time_str, task, type, icon, done, reminder_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, time_str, _enc(task), rtype, icon, done, today),
            )
    conn.commit()

    # 21 days of synthetic game-score history so the AI trend engine has
    # something real to analyse. Patient 1 trends DOWN (to demonstrate an
    # alert); patient 2 is stable; patient 3 trends UP.
    game_types = ["memory_match", "pattern_recall", "traditions_match"]
    trend_profile = {
        patient_ids[0]: -1.6,   # declining
        patient_ids[1]: 0.05,   # stable
        patient_ids[2]: 1.1,    # improving
    }
    random.seed(42)
    for pid in patient_ids:
        base = 65
        slope = trend_profile[pid]
        for day_offset in range(21, 0, -1):
            played_at = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d %H:%M:%S")
            day_index = 21 - day_offset
            for game in game_types:
                noise = random.uniform(-6, 6)
                score = base + slope * day_index + noise
                score = max(5, min(100, score))
                cur.execute(
                    "INSERT INTO game_scores (patient_id, game_type, score, max_score, played_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pid, game, round(score, 1), 100, played_at),
                )
    conn.commit()


def _top_up_game_scores(conn, game_types=("memory_match", "pattern_recall", "traditions_match")):
    """Demo/seed data is only ever as fresh as the day it was generated --
    left alone, every chart and trend alert goes stale (empty "last 24
    hours" view, trend line stuck days in the past) the moment real time
    moves on. Called on every init_db(), this extends each patient's
    existing score history up through "now", continuing whatever trend is
    already in their data (a simple linear fit) rather than resetting it,
    and adds a few sessions in the last several hours so the 24-hour chart
    always has something to show. Skipped for patients with no score
    history yet (nothing to extend) or whose data is already fresh."""
    cur = conn.cursor()
    now = datetime.now()
    patient_ids = [row[0] for row in cur.execute("SELECT id FROM patients ORDER BY id")]

    for pid in patient_ids:
        rows = cur.execute(
            "SELECT played_at, score FROM game_scores WHERE patient_id = ? ORDER BY played_at",
            (pid,),
        ).fetchall()
        if len(rows) < 3:
            continue

        last_played = datetime.strptime(rows[-1]["played_at"], "%Y-%m-%d %H:%M:%S")
        if (now - last_played) < timedelta(hours=20):
            continue

        by_day = {}
        for r in rows:
            by_day.setdefault(r["played_at"][:10], []).append(r["score"])
        days_sorted = sorted(by_day)
        daily_avg = [sum(by_day[d]) / len(by_day[d]) for d in days_sorted]

        if len(daily_avg) >= 2:
            xs = list(range(len(daily_avg)))
            mean_x, mean_y = sum(xs) / len(xs), sum(daily_avg) / len(daily_avg)
            denom = sum((x - mean_x) ** 2 for x in xs)
            slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, daily_avg)) / denom if denom else 0.0
        else:
            slope = 0.0
        base = daily_avg[-1]

        missing_days = (now.date() - last_played.date()).days
        for d in range(1, missing_days):
            day = last_played + timedelta(days=d)
            for game in game_types:
                score = max(5, min(100, base + slope * d + random.uniform(-6, 6)))
                played_at = day.replace(hour=random.randint(9, 20), minute=random.randint(0, 59), second=0)
                cur.execute(
                    "INSERT INTO game_scores (patient_id, game_type, score, max_score, played_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pid, game, round(score, 1), 100, played_at.strftime("%Y-%m-%d %H:%M:%S")),
                )

        for i, hrs_ago in enumerate([7, 5, 3, 1.5, 0.5]):
            game = game_types[i % len(game_types)]
            score = max(5, min(100, base + slope * missing_days + random.uniform(-6, 6)))
            played_at = now - timedelta(hours=hrs_ago)
            cur.execute(
                "INSERT INTO game_scores (patient_id, game_type, score, max_score, played_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, game, round(score, 1), 100, played_at.strftime("%Y-%m-%d %H:%M:%S")),
            )

    conn.commit()


# ---------------------------------------------------------------- helpers --

def patient_location(patient):
    """Display string combining village + state, e.g. 'Sonapur, Assam' --
    for the 3 demo patients the state is already typed into `village` by
    hand, so this avoids double-showing it; for a patient registered
    through the app, `village` is just the plain town name and `state` is
    the separate structured field, so this is what actually shows the
    state anywhere (sidebar, caregiver dashboard, PDF report)."""
    village = (patient["village"] or "").strip()
    state_name = STATES.get(patient["state"], "")
    if state_name and state_name.lower() not in village.lower():
        return f"{village}, {state_name}" if village else state_name
    return village


def get_patients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients ORDER BY id").fetchall()
    conn.close()
    patients = [dict(r) for r in rows]
    for p in patients:
        p["name"] = _dec(p["name"])
        p["village"] = _dec(p["village"])
    return patients


def add_patient(name, age, village, language, state, pin, photo_path=None):
    """Register a new patient with a caregiver-chosen PIN (hashed before
    storage, never kept in plain text). `language` is UI translation only;
    `state` (a STATES code) is what drives 'Know Your Roots' content --
    they're independent so a patient can read the app in English while
    still seeing their own state's culture in the game. Returns the new
    patient's id."""
    salt = _new_salt()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO patients (name, age, village, language, state, pin, pin_salt, photo_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_enc(name), age, _enc(village), language, state, _hash_pin(pin, salt), salt, photo_path),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def verify_patient_pin(patient, pin):
    """Check a login attempt's PIN against the patient's stored hash. Takes
    the already-fetched patient row (as returned by get_patients()) rather
    than re-querying, since the caller already has it from the login form."""
    return _hash_pin(pin, patient["pin_salt"]) == patient["pin"]


def verify_admin_pin(pin):
    """Check the local caregiver admin PIN used for the offline 'forgot
    PIN' flow (see reset_patient_pin)."""
    conn = get_conn()
    row = conn.execute("SELECT pin_hash, pin_salt FROM app_admin WHERE id = 1").fetchone()
    conn.close()
    return bool(row) and _hash_pin(pin, row["pin_salt"]) == row["pin_hash"]


def reset_patient_pin(patient_id):
    """Generate a fresh random 4-digit PIN for a patient, store it hashed,
    and return the plain-text value once so it can be shown on screen and
    written down -- the offline equivalent of a password-reset email, but
    entirely local. Only call after verify_admin_pin() has succeeded."""
    new_pin = f"{random.randint(0, 9999):04d}"
    salt = _new_salt()
    conn = get_conn()
    conn.execute(
        "UPDATE patients SET pin = ?, pin_salt = ? WHERE id = ?",
        (_hash_pin(new_pin, salt), salt, patient_id),
    )
    conn.commit()
    conn.close()
    return new_pin


def update_patient_photo(patient_id, photo_path):
    """Set (or clear, with photo_path=None) a patient's photo. Cleans up the
    previous uploaded file so replacing/removing a photo doesn't leave
    orphaned files accumulating in photos/uploads/."""
    conn = get_conn()
    old = conn.execute("SELECT photo_path FROM patients WHERE id = ?", (patient_id,)).fetchone()
    conn.execute("UPDATE patients SET photo_path = ? WHERE id = ?", (photo_path, patient_id))
    conn.commit()
    conn.close()
    if old and old["photo_path"] and old["photo_path"] != photo_path:
        delete_uploaded_photo(old["photo_path"])


def get_family(patient_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM family_members WHERE patient_id = ? ORDER BY id", (patient_id,)
    ).fetchall()
    conn.close()
    family = [dict(r) for r in rows]
    for f in family:
        f["name"] = _dec(f["name"])
        f["note"] = _dec(f["note"])
    return family


def get_traditions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM traditions ORDER BY id").fetchall()
    conn.close()
    return rows


def get_traditions_for_state(state):
    """Traditions matching a patient's own state/culture, for the 'Know
    Your Roots' game -- e.g. a patient from Assam gets exactly their 3
    Assam items, not a mixed pan-NER set, regardless of what UI language
    they've chosen to read the app in. Falls back to the full mixed list
    only when state is unset entirely (no state selected at all) -- a
    patient whose state IS set but has no dedicated content yet gets an
    empty result rather than another state's culture mislabeled as their
    own; the caller shows a message asking the caregiver to add content
    for that specific state instead."""
    rows = get_traditions()
    if not state:
        return rows
    specific = [r for r in rows if r["language"] == state]
    if len(specific) >= 3:
        return specific
    generic = [r for r in rows if not r["language"]]
    return specific + generic


def add_tradition(name, category, note="", photo_path=None, language=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO traditions (name, category, note, photo_path, language) VALUES (?, ?, ?, ?, ?)",
        (name, category, note or "A tradition of the North Eastern Region.", photo_path, language),
    )
    conn.commit()
    conn.close()


def add_family_member(patient_id, name, relation, note="", photo_path=None):
    initials = "".join([w[0] for w in name.split()][:2]).upper()
    conn = get_conn()
    conn.execute(
        "INSERT INTO family_members (patient_id, name, relation, initials, last_contact, note, photo_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (patient_id, _enc(name), relation, initials, "Added just now",
         _enc(note or "A cherished person in your life."), photo_path),
    )
    conn.commit()
    conn.close()


def save_uploaded_photo(file_bytes, original_filename):
    """Validate, downscale and save an uploaded photo into photos/uploads/,
    returning the relative path to store in the database.

    Every upload is re-encoded as a capped-size JPEG (max 512px on the long
    edge) regardless of what was uploaded -- this keeps per-photo storage
    small and predictable rather than trusting whatever size/format the
    browser sent, and raises a clear error for a file that isn't really an
    image rather than silently saving garbage bytes."""
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(BytesIO(file_bytes))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise ValueError("That file doesn't look like a valid image.")

    img = img.convert("RGB")
    max_dim = 512
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    uploads_dir = os.path.join(PHOTOS_DIR, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    img.save(os.path.join(uploads_dir, filename), "JPEG", quality=85)
    return f"photos/uploads/{filename}"


def delete_uploaded_photo(photo_path):
    """Remove a previously uploaded photo from disk. Only ever deletes files
    under photos/uploads/ -- never touches the bundled demo avatars that
    live directly under photos/."""
    if not photo_path or not photo_path.replace("\\", "/").startswith("photos/uploads/"):
        return
    full_path = os.path.join(os.path.dirname(__file__), photo_path)
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except OSError:
        pass


def get_reminders(patient_id, date_str=None):
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM reminders WHERE patient_id = ? AND reminder_date = ? ORDER BY id",
        (patient_id, date_str),
    ).fetchall()
    if not rows:
        rows = _roll_reminders_forward(conn, patient_id, date_str)
    conn.close()
    reminders = [dict(r) for r in rows]
    for r in reminders:
        r["task"] = _dec(r["task"])
    return reminders


def _roll_reminders_forward(conn, patient_id, date_str):
    """Reminders are meant to recur daily. If a patient has no reminders yet
    for date_str, copy forward their most recent day's reminder list (fresh,
    with done reset to 0) instead of leaving them with an empty list -- a
    fixed reminder_date otherwise means every reminder permanently vanishes
    the day after it was created/seeded."""
    cur = conn.cursor()
    last_date_row = cur.execute(
        "SELECT MAX(reminder_date) AS d FROM reminders WHERE patient_id = ? AND reminder_date < ?",
        (patient_id, date_str),
    ).fetchone()
    last_date = last_date_row["d"] if last_date_row else None
    if not last_date:
        return []

    prev_rows = cur.execute(
        "SELECT time_str, task, type, icon FROM reminders WHERE patient_id = ? AND reminder_date = ? ORDER BY id",
        (patient_id, last_date),
    ).fetchall()
    for r in prev_rows:
        cur.execute(
            "INSERT INTO reminders (patient_id, time_str, task, type, icon, done, reminder_date) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (patient_id, r["time_str"], r["task"], r["type"], r["icon"], date_str),
        )
    conn.commit()
    return cur.execute(
        "SELECT * FROM reminders WHERE patient_id = ? AND reminder_date = ? ORDER BY id",
        (patient_id, date_str),
    ).fetchall()


def set_reminder_done(reminder_id, done):
    conn = get_conn()
    conn.execute("UPDATE reminders SET done = ? WHERE id = ?", (int(done), reminder_id))
    conn.commit()
    conn.close()


def add_reminder(patient_id, time_str, task, rtype="Custom", icon="📌"):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    conn.execute(
        "INSERT INTO reminders (patient_id, time_str, task, type, icon, done, reminder_date) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (patient_id, time_str, _enc(task), rtype, icon, today),
    )
    conn.commit()
    conn.close()


def log_game_score(patient_id, game_type, score, max_score=100):
    conn = get_conn()
    conn.execute(
        "INSERT INTO game_scores (patient_id, game_type, score, max_score, played_at) VALUES (?, ?, ?, ?, ?)",
        (patient_id, game_type, score, max_score, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_scores(patient_id, game_type=None, days=21):
    conn = get_conn()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    if game_type:
        rows = conn.execute(
            "SELECT * FROM game_scores WHERE patient_id = ? AND game_type = ? AND played_at >= ? ORDER BY played_at",
            (patient_id, game_type, since),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM game_scores WHERE patient_id = ? AND played_at >= ? ORDER BY played_at",
            (patient_id, since),
        ).fetchall()
    conn.close()
    return rows
