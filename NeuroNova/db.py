"""
db.py — SQLite data layer for Neuronova
Handles schema creation, demo-data seeding, and all CRUD helpers
used by the Streamlit UI (frontend.py) and the AI engine (cognitive_ai.py).
"""

import sqlite3
import os
import random
import uuid
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "NeuroNova.db")
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")

# Languages supported for a patient's preferred language, keyed by the code
# stored in patients.language. Native names included for display purposes.
LANGUAGES = {
    "en": "English",
    "as": "Assamese (অসমীয়া)",
    "kha": "Khasi",
    "brx": "Bodo (बड़ो)",
    "mni": "Manipuri / Meitei (মৈতৈলোন্)",
    "lus": "Mizo (Mizo ṭawng)",
}


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
            pin TEXT DEFAULT '1234',
            photo_path TEXT
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

    family_cols = [row[1] for row in cur.execute("PRAGMA table_info(family_members)")]
    if "photo_path" not in family_cols:
        cur.execute("ALTER TABLE family_members ADD COLUMN photo_path TEXT")
        conn.commit()

    os.makedirs(PHOTOS_DIR, exist_ok=True)

    if first_run or force_reseed:
        _seed_demo_data(conn)

    _top_up_game_scores(conn)

    conn.close()


def _seed_demo_data(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM game_scores")
    cur.execute("DELETE FROM reminders")
    cur.execute("DELETE FROM family_members")
    cur.execute("DELETE FROM patients")

    patients = [
        ("Ratan Bora", 74, "Sonapur, Assam", "as", "photos/demo_ratan_bora.png"),
        ("Ma Kiimi Lyngdoh", 69, "Mawlai, Meghalaya", "kha", "photos/demo_ma_kiimi_lyngdoh.png"),
        ("L. Ibemhal Singh", 78, "Imphal, Manipur", "mni", "photos/demo_l_ibemhal_singh.png"),
    ]
    cur.executemany(
        "INSERT INTO patients (name, age, village, language, photo_path) VALUES (?, ?, ?, ?, ?)",
        patients,
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
                (pid, name, relation, initials, last, note, photo_path),
            )
    conn.commit()

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
                (pid, time_str, task, rtype, icon, done, today),
            )
    conn.commit()

    # 21 days of synthetic game-score history so the AI trend engine has
    # something real to analyse. Patient 1 trends DOWN (to demonstrate an
    # alert); patient 2 is stable; patient 3 trends UP.
    game_types = ["memory_match", "pattern_recall", "family_match"]
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


def _top_up_game_scores(conn, game_types=("memory_match", "pattern_recall", "family_match")):
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

def get_patients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients ORDER BY id").fetchall()
    conn.close()
    return rows


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
    return rows


def add_family_member(patient_id, name, relation, note="", photo_path=None):
    initials = "".join([w[0] for w in name.split()][:2]).upper()
    conn = get_conn()
    conn.execute(
        "INSERT INTO family_members (patient_id, name, relation, initials, last_contact, note, photo_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (patient_id, name, relation, initials, "Added just now", note or "A cherished person in your life.", photo_path),
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
    return rows


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
        (patient_id, time_str, task, rtype, icon, today),
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
