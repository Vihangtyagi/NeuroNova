"""
db.py — SQLite data layer for Neuronova
Handles schema creation, demo-data seeding, and all CRUD helpers
used by the Streamlit UI (frontend.py) and the AI engine (cognitive_ai.py).
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "NeuroNova.db")

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
            language TEXT DEFAULT 'en'
        );

        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            relation TEXT NOT NULL,
            initials TEXT,
            last_contact TEXT,
            note TEXT,
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

    if first_run or force_reseed:
        _seed_demo_data(conn)

    conn.close()


def _seed_demo_data(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM game_scores")
    cur.execute("DELETE FROM reminders")
    cur.execute("DELETE FROM family_members")
    cur.execute("DELETE FROM patients")

    patients = [
        ("Ratan Bora", 74, "Sonapur, Assam", "as"),
        ("Ma Kiimi Lyngdoh", 69, "Mawlai, Meghalaya", "kha"),
        ("L. Ibemhal Singh", 78, "Imphal, Manipur", "mni"),
    ]
    cur.executemany(
        "INSERT INTO patients (name, age, village, language) VALUES (?, ?, ?, ?)",
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
            cur.execute(
                "INSERT INTO family_members (patient_id, name, relation, initials, last_contact, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, relation, initials, last, note),
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


# ---------------------------------------------------------------- helpers --

def get_patients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients ORDER BY id").fetchall()
    conn.close()
    return rows


def get_family(patient_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM family_members WHERE patient_id = ? ORDER BY id", (patient_id,)
    ).fetchall()
    conn.close()
    return rows


def add_family_member(patient_id, name, relation, note=""):
    initials = "".join([w[0] for w in name.split()][:2]).upper()
    conn = get_conn()
    conn.execute(
        "INSERT INTO family_members (patient_id, name, relation, initials, last_contact, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (patient_id, name, relation, initials, "Added just now", note or "A cherished person in your life."),
    )
    conn.commit()
    conn.close()


def get_reminders(patient_id, date_str=None):
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM reminders WHERE patient_id = ? AND reminder_date = ? ORDER BY id",
        (patient_id, date_str),
    ).fetchall()
    conn.close()
    return rows


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
