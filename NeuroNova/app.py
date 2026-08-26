"""
Smriti Sathi — AI-Based Cognitive Gaming & Memory Assistance Platform
for Elderly Dementia Patients in the North Eastern Region (SIH26003)

Run with:  streamlit run app.py
"""

import random
import streamlit as st
import pandas as pd

import db
import cognitive_ai
import voice

st.set_page_config(page_title="Neuronova", page_icon="🪔", layout="centered")
db.init_db()

# NOTE on translation quality: "en" and "as" (Assamese) are solid. The "kha"
# (Khasi), "brx" (Bodo), "mni" (Manipuri/Meitei) and "lus" (Mizo) entries
# below are AI best-effort drafts, NOT verified by native speakers — treat
# them as placeholders to be reviewed before real patient-facing use.
LABELS = {
    "en": {"app": "Neuronova", "sub": "Memory Companion · North Eastern Region",
           "greeting": "Good Morning", "games": "Play Memory Games", "box": "My Memory Box",
           "reminders": "Today's Reminders", "call": "Call Family"},
    "as": {"app": "Neuronova", "sub": "মেমোৰি কম্পেনিয়ন · উত্তৰ পূৰ্বাঞ্চল",
           "greeting": "শুভ প্ৰভাত", "games": "স্মৃতি খেল", "box": "মোৰ স্মৃতি বাকচ",
           "reminders": "আজিৰ মনত পেলোৱা", "call": "পৰিয়ালক কল কৰক"},
    "kha": {"app": "Neuronova", "sub": "Nongïarap Kynmaw · Ri Khasi–Jaiñtia",
            "greeting": "Mih Shaphrang", "games": "Khena Kynmaw", "box": "Ka Bokso Kynmaw Jong Nga",
            "reminders": "Ka Kynmaw Mynta", "call": "Kyllum Ïing"},
    "brx": {"app": "Neuronova", "sub": "सोदोबनायाव फुंखा · बर'लैंड",
            "greeting": "गुबुन सान", "games": "सोदोब आन्जोरनाय गेम", "box": "आं'नि सोदोब बाक्सा",
            "reminders": "दिनैनि खोन्दोब", "call": "फिसाजोबो फोन"},
    "mni": {"app": "Neuronova", "sub": "মৈতৈলোন্ · মণিপুর",
            "greeting": "নুংঙাইবা য়েংথোক্কী", "games": "নীংশিং খেল থাগৎপা", "box": "ঐগী নীংশিং বক্স",
            "reminders": "ঙসিগী ৱারোল", "call": "ইমুং কল তৌবা"},
    "lus": {"app": "Neuronova", "sub": "Hriatna Ṭhian · Zoram",
            "greeting": "Chibai", "games": "Hriatna Inen", "box": "Ka Hriatna Bâwm",
            "reminders": "Tunlaia Hriattîrna", "call": "Chhungkaw Ko"},
}

GAME_TYPES = {"memory_match": "Memory Match", "pattern_recall": "Pattern Recall", "family_match": "Who Is This?"}
SYMBOLS = ["🍵", "🐘", "🛶", "🥁", "🌾", "🎭"]
PADS = ["Tea Garden", "Muga Silk", "River Boat", "Bihu Drum"]

# ----------------------------------------------------------------- state --
ss = st.session_state
ss.setdefault("page", "welcome")
ss.setdefault("lang", "en")
ss.setdefault("role", "Patient")

patients = db.get_patients()
patient_names = [p["name"] for p in patients]
ss.setdefault("patient_id", patients[0]["id"])


def goto(page):
    ss.page = page
    st.rerun()


def L(key):
    return LABELS[ss.lang][key]


def current_patient():
    return next(p for p in patients if p["id"] == ss.patient_id)


def speak_button(text, key):
    if st.button("🔊 Play aloud", key=key):
        if voice.is_available():
            path = voice.speak_to_file(text)
            if path:
                st.audio(path)
            else:
                st.info(text)
        else:
            st.info(f"(voice engine unavailable here) — \"{text}\"")


def render_add_reminder_form(patient_id, key_suffix):
    with st.expander("+ Add reminder"):
        with st.form(f"add_reminder_form_{key_suffix}", clear_on_submit=True):
            time_str = st.text_input("Time (e.g. 06:00 PM)", key=f"rem_time_{key_suffix}")
            task = st.text_input("Task (e.g. Evening walk)", key=f"rem_task_{key_suffix}")
            rtype = st.selectbox(
                "Type", ["Medicine", "Meal", "Activity", "Family", "Custom"], key=f"rem_type_{key_suffix}"
            )
            if st.form_submit_button("Save reminder"):
                if time_str and task:
                    icon = {"Medicine": "💊", "Meal": "🍚", "Activity": "🧩", "Family": "📞", "Custom": "📌"}[rtype]
                    db.add_reminder(patient_id, time_str, task, rtype, icon)
                    st.success("Reminder added")
                    st.rerun()
                else:
                    st.warning("Please enter both a time and a task.")


def icon_badge_html(emoji, bg, size="md"):
    cls = "ss-badge" if size == "md" else "ss-badge ss-badge-sm"
    return f'<div class="{cls}" style="background:{bg};">{emoji}</div>'


def avatar_html(initials):
    return f'<div class="ss-avatar">{initials}</div>'


def render_tile(emoji, badge_bg, title, subtitle, button_label, key, on_click_page, disabled=False):
    """A card-style navigation tile: icon badge + title + subtitle + CTA button."""
    with st.container(border=True):
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                {icon_badge_html(emoji, badge_bg)}
                <div>
                    <div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-dark);">{title}</div>
                    <div style="font-size:0.85rem;color:var(--ss-text-muted);">{subtitle}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(button_label, key=key, use_container_width=True, disabled=disabled):
            goto(on_click_page)


def render_risk_banner(risk, recommendation):
    tone = {
        "High": ("var(--ss-risk-high)", "#fdecea", "⚠️"),
        "Medium": ("var(--ss-risk-medium)", "#fdf3e2", "🔶"),
        "Low": ("var(--ss-risk-low)", "#e9f7ee", "✅"),
        "Unknown": ("var(--ss-text-muted)", "#f1efe8", "ℹ️"),
    }
    color, bg, icon = tone.get(risk, tone["Unknown"])
    st.markdown(
        f"""
        <div style="background:{bg};border-left:6px solid {color};border-radius:14px;
                    padding:1.1rem 1.3rem;display:flex;gap:0.9rem;align-items:flex-start;
                    box-shadow:0 6px 16px rgba(20,99,86,0.08);margin-bottom:1rem;">
            <div style="font-size:1.5rem;line-height:1;">{icon}</div>
            <div>
                <div style="font-weight:700;color:{color};font-size:1.05rem;">Risk level: {risk}</div>
                <div style="color:var(--ss-text);margin-top:0.2rem;">{recommendation}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trend_pill(trend):
    tone = {
        "Improving": ("var(--ss-risk-low)", "#e9f7ee", "📈"),
        "Stable": ("var(--ss-primary)", "#eaf3ee", "➖"),
        "Declining": ("var(--ss-risk-high)", "#fdecea", "📉"),
    }
    color, bg, icon = tone.get(trend, ("var(--ss-text-muted)", "#f1efe8", "❔"))
    st.markdown(
        f"""<span style="background:{bg};color:{color};border:1.5px solid {color};
              border-radius:999px;padding:0.25rem 0.8rem;font-weight:700;font-size:0.85rem;
              display:inline-flex;align-items:center;gap:0.35rem;">{icon} {trend}</span>""",
        unsafe_allow_html=True,
    )


def inject_global_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

        :root {
            --ss-primary: #146356;
            --ss-primary-dark: #0c4238;
            --ss-primary-light: #2f9c85;
            --ss-secondary: #6b4fa0;
            --ss-secondary-dark: #4f3878;
            --ss-accent: #ff8659;
            --ss-accent-dark: #ea6a3a;
            --ss-gold: #d9a441;
            --ss-bg: #f6f3ec;
            --ss-bg-alt: #ece5d6;
            --ss-card: #ffffff;
            --ss-text: #20342f;
            --ss-text-muted: #66766f;
            --ss-risk-high: #c94b3f;
            --ss-risk-medium: #d99a2b;
            --ss-risk-low: #2f9c66;
        }

        html { font-size: 19px; }
        html, body, [class*="css"] {
            font-family: 'Poppins', sans-serif;
            color: var(--ss-text);
            line-height: 1.6;
        }
        p, li, span, label { line-height: 1.6; }

        .stApp {
            background:
                radial-gradient(circle at 6% 0%, rgba(20,99,86,0.10), transparent 34%),
                radial-gradient(circle at 96% 8%, rgba(255,134,89,0.12), transparent 38%),
                radial-gradient(circle at 15% 88%, rgba(107,79,160,0.08), transparent 36%),
                radial-gradient(circle at 90% 92%, rgba(217,164,65,0.10), transparent 34%),
                linear-gradient(180deg, var(--ss-bg) 0%, var(--ss-bg-alt) 100%);
            background-attachment: fixed;
        }

        /* Safety net: every screen in this app now has a light background, so nothing should
           ever render white/near-white text. Low-specificity catch-all — anything more specific
           below (buttons, chips, muted captions) still wins the cascade and keeps its own color. */
        .stApp * { color: var(--ss-text); }

        /* Every rerun re-mounts the main block — give it a soft entrance instead of a hard cut. */
        @media (prefers-reduced-motion: no-preference) {
            .main .block-container {
                animation: ss-enter 0.45s cubic-bezier(0.16, 1, 0.3, 1);
            }
        }
        @keyframes ss-enter {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--ss-primary-light); border-radius: 999px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--ss-primary); }

        .ss-badge {
            display: inline-flex; align-items: center; justify-content: center;
            width: 3.1rem; height: 3.1rem; border-radius: 16px;
            font-size: 1.5rem; flex: none;
            box-shadow: 0 6px 14px rgba(20,99,86,0.22);
        }
        .ss-badge-sm { width: 2.4rem; height: 2.4rem; border-radius: 12px; font-size: 1.15rem; }

        .ss-avatar {
            display: inline-flex; align-items: center; justify-content: center;
            width: 2.6rem; height: 2.6rem; border-radius: 999px; flex: none;
            font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 1rem;
            color: var(--ss-primary-dark);
            background: linear-gradient(135deg, #eaf3ee 0%, #f1e9fb 100%);
            border: 2px solid var(--ss-primary);
            box-shadow: 0 4px 10px rgba(20,99,86,0.18);
        }

        /* Sidebar: light card look, not a dark panel, so nothing reads as white-on-dark. */
        section[data-testid="stSidebar"] {
            background: var(--ss-card);
            border-right: 4px solid var(--ss-primary);
        }
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: var(--ss-primary-dark) !important;
        }
        section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span {
            color: var(--ss-text) !important;
            font-weight: 500;
        }

        h1, h2, h3 { font-family: 'Poppins', sans-serif; color: var(--ss-primary-dark); font-weight: 700; }
        h1 { font-size: 2.1rem; }
        h2 { font-size: 1.6rem; }
        h3 { font-size: 1.3rem; }

        /* Buttons: bold colour outline + colour text on a light fill. No white text anywhere.
           Covers plain buttons AND form-submit buttons, which Streamlit renders separately. */
        div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button {
            background: #fff3ec;
            color: var(--ss-accent-dark);
            border: 2.5px solid var(--ss-accent-dark);
            border-radius: 14px;
            padding: 0.85rem 1.6rem;
            font-family: 'Poppins', sans-serif;
            font-weight: 700;
            font-size: 1.05rem;
            box-shadow: 0 6px 14px rgba(194,87,48,0.16);
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
        }
        div[data-testid="stButton"] button p, div[data-testid="stFormSubmitButton"] button p {
            font-weight: 700; font-size: 1.05rem; color: var(--ss-accent-dark);
        }
        div[data-testid="stButton"] button:hover, div[data-testid="stFormSubmitButton"] button:hover {
            background: #ffe4d4;
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(194,87,48,0.24);
        }
        div[data-testid="stButton"] button:disabled, div[data-testid="stFormSubmitButton"] button:disabled {
            background: #ece7dc;
            color: #a49c89;
            border-color: #d8d2c4;
            box-shadow: none;
            transform: none;
        }

        /* Dropdown popovers (select widgets) render at document root — force dark, readable text
           even on the highlighted/selected option, which BaseWeb otherwise shows in white. */
        ul[role="listbox"] li, ul[role="listbox"] li * {
            color: var(--ss-text) !important;
        }
        ul[role="listbox"] li[aria-selected="true"] {
            background: #fff3ec !important;
            color: var(--ss-accent-dark) !important;
        }
        ul[role="listbox"] li[aria-selected="true"] * { color: var(--ss-accent-dark) !important; }

        /* Toasts (st.toast) default to a dark bubble with white text. */
        div[data-testid="stToast"] {
            background: var(--ss-card) !important;
            border: 1.5px solid var(--ss-primary);
        }
        div[data-testid="stToast"] * { color: var(--ss-text) !important; }

        div[data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--ss-card);
            border-radius: 16px;
            box-shadow: 0 6px 18px rgba(20,99,86,0.1);
            border: 1px solid rgba(20,99,86,0.08);
        }
        div[data-testid="stMetric"] { padding: 0.9rem 1.1rem; }
        div[data-testid="stMetric"] label, div[data-testid="stMetricLabel"] { color: var(--ss-text-muted) !important; }
        div[data-testid="stMetricValue"] { color: var(--ss-primary-dark) !important; }

        div[data-testid="stExpander"] {
            background: var(--ss-card);
            border-radius: 14px;
            border: 1px solid rgba(20,99,86,0.12);
        }

        div[data-testid="stAlert"] p { font-size: 1.02rem; line-height: 1.6; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_welcome():
    st.write("")
    st.write("")
    st.write("")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(
            """
            <div style="background:var(--ss-card);border-radius:24px;padding:2.6rem 2rem;
                        text-align:center;box-shadow:0 14px 32px rgba(20,99,86,0.14);
                        border:1px solid rgba(20,99,86,0.08);">
                <div style="font-size:3rem;">🪔</div>
                <h2 style="margin:0.6rem 0 0.3rem;color:var(--ss-primary-dark);">Hi there 👋</h2>
                <p style="color:var(--ss-text-muted);margin:0;">Welcome to Neuronova. Tap Enter when you're ready.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("Enter", use_container_width=True):
            ss.page = "landing"
            st.rerun()


def render_landing():
    if st.button("← Back"):
        ss.page = "welcome"
        st.rerun()

    st.markdown(
        """
        <style>
        .ss-hero {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at 90% -10%, rgba(255,134,89,0.28), transparent 45%),
                radial-gradient(circle at -10% 110%, rgba(20,99,86,0.22), transparent 45%),
                linear-gradient(135deg, #fdf9f0 0%, #f3ecda 100%);
            border: 2px solid rgba(20,99,86,0.12);
            border-radius: 28px;
            padding: 3.2rem 2rem 2.6rem;
            text-align: center;
            color: var(--ss-text);
            box-shadow: 0 18px 40px rgba(20, 99, 86, 0.14);
        }
        .ss-diya {
            font-size: 4.4rem;
            display: inline-block;
            animation: ss-flicker 2.4s ease-in-out infinite;
            filter: drop-shadow(0 0 20px rgba(255, 134, 89, 0.55));
        }
        @keyframes ss-flicker {
            0%, 100% { transform: scale(1) translateY(0); opacity: 1; }
            50% { transform: scale(1.08) translateY(-3px); opacity: 0.88; }
        }
        .ss-hero h1 {
            font-family: 'Poppins', sans-serif;
            font-size: 2.8rem;
            margin: 0.6rem 0 0.3rem;
            letter-spacing: 0.5px;
            color: var(--ss-primary-dark);
        }
        .ss-hero p.ss-tagline {
            font-family: 'Poppins', sans-serif;
            font-size: 1.15rem;
            color: var(--ss-text);
            margin: 0;
            font-weight: 500;
        }
        .ss-chips { margin-top: 1.5rem; display: flex; flex-wrap: wrap; justify-content: center; gap: 0.5rem; }
        .ss-chip {
            background: #ffffff;
            border: 1.5px solid var(--ss-primary);
            color: var(--ss-primary-dark);
            border-radius: 999px;
            padding: 0.35rem 1rem;
            font-size: 0.88rem;
            font-weight: 600;
            font-family: 'Poppins', sans-serif;
        }
        .ss-features { display: flex; gap: 1rem; margin-top: 1.8rem; flex-wrap: wrap; }
        .ss-card {
            flex: 1 1 150px;
            background: var(--ss-card);
            border-radius: 18px;
            padding: 1.3rem 1rem;
            text-align: center;
            box-shadow: 0 8px 20px rgba(20,99,86,0.1);
            border: 1px solid rgba(20,99,86,0.08);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .ss-card:hover { transform: translateY(-3px); box-shadow: 0 12px 26px rgba(20,99,86,0.16); }
        .ss-card .ss-icon { font-size: 2rem; }
        .ss-card h4 { font-family: 'Poppins', sans-serif; margin: 0.4rem 0 0.2rem; color: var(--ss-primary-dark); font-size: 1rem; }
        .ss-card p { margin: 0; font-size: 0.82rem; color: var(--ss-text-muted); }
        </style>
        """,
        unsafe_allow_html=True,
    )

    chips = "".join(f'<span class="ss-chip">{name}</span>' for name in db.LANGUAGES.values())
    st.markdown(
        f"""
        <div class="ss-hero">
            <span class="ss-diya">🪔</span>
            <h1>Neuronova</h1>
            <p class="ss-tagline">A gentle memory companion for elders across the North Eastern Region</p>
            <div class="ss-chips">{chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ss-features">
            <div class="ss-card"><div class="ss-icon">🧩</div><h4>Memory Games</h4>
                <p>Gentle daily play to keep the mind active</p></div>
            <div class="ss-card"><div class="ss-icon">🖼️</div><h4>Memory Box</h4>
                <p>Familiar faces and loving notes, always close by</p></div>
            <div class="ss-card"><div class="ss-icon">⏰</div><h4>Reminders</h4>
                <p>Medicine, meals and family calls, right on time</p></div>
            <div class="ss-card"><div class="ss-icon">📊</div><h4>Caregiver Insights</h4>
                <p>Trends and gentle alerts for the family</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    st.write("")
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if st.button("✨  Enter Neuronova", use_container_width=True):
            ss.page = "home"
            st.rerun()
    st.caption("SIH26003 — working prototype")


inject_global_css()

if ss.page == "welcome":
    render_welcome()
    st.stop()

if ss.page == "landing":
    render_landing()
    st.stop()

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.6rem;">
            <div class="ss-badge ss-badge-sm"
                 style="background:linear-gradient(135deg,#eaf3ee,#f1e9fb);border:2px solid var(--ss-primary);">🪔</div>
            <div style="font-family:'Poppins',sans-serif;font-weight:800;font-size:1.3rem;color:var(--ss-primary-dark);">
                Neuronova</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ss.role = st.radio("View", ["Patient", "Caregiver"], index=["Patient", "Caregiver"].index(ss.role))

    sel_name = st.selectbox("Demo profile", patient_names, index=patient_names.index(current_patient()["name"]))
    new_patient = next(p for p in patients if p["name"] == sel_name)
    if new_patient["id"] != ss.patient_id and new_patient["language"] in LABELS:
        ss.lang = new_patient["language"]
    ss.patient_id = new_patient["id"]

    initials = "".join(w[0] for w in new_patient["name"].split()[:2]).upper()
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.7rem;background:var(--ss-card);
                    border:1px solid rgba(20,99,86,0.12);border-radius:14px;padding:0.7rem 0.9rem;
                    margin:0.5rem 0 0.9rem;box-shadow:0 4px 12px rgba(20,99,86,0.06);">
            {avatar_html(initials)}
            <div>
                <div style="font-weight:700;color:var(--ss-primary-dark);">{new_patient['name']}</div>
                <div style="font-size:0.8rem;color:var(--ss-text-muted);">{new_patient['village']} &middot; age {new_patient['age']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    lang_codes = list(LABELS.keys())
    ss.lang = st.selectbox(
        "Language", lang_codes, index=lang_codes.index(ss.lang),
        format_func=lambda c: db.LANGUAGES.get(c, c),
    )
    st.caption("SIH26003 — working prototype")

patient = current_patient()

# =========================================================== CAREGIVER ===
if ss.role == "Caregiver":
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.3rem;">
            {icon_badge_html('📊', 'linear-gradient(135deg,var(--ss-secondary),var(--ss-secondary-dark))')}
            <div>
                <div style="font-family:'Poppins',sans-serif;font-weight:800;font-size:1.7rem;
                            color:var(--ss-primary-dark);line-height:1.1;">Caregiver Dashboard</div>
                <div style="color:var(--ss-text-muted);">
                    Monitoring <b style="color:var(--ss-text);">{patient['name']}</b>,
                    age {patient['age']} &middot; {patient['village']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    reminders_today = db.get_reminders(patient["id"])
    adherence_pct, meds_done, meds_total = cognitive_ai.medicine_adherence(reminders_today)

    scores = db.get_scores(patient["id"])
    trend = cognitive_ai.analyze_trend(scores)

    c1, c2, c3 = st.columns(3)
    metric_specs = [
        (c1, "🎯", "var(--ss-primary)", "7-day avg engagement",
         f"{trend['recent_avg']:.0f}%" if trend["has_data"] else "—"),
        (c2, "📈", "var(--ss-secondary)", "Trend", trend["trend"]),
        (c3, "💊", "var(--ss-accent-dark)", "Medicine adherence today", f"{meds_done}/{meds_total}"),
    ]
    for col, emoji, color, label, value in metric_specs:
        with col:
            with st.container(border=True):
                st.markdown(icon_badge_html(emoji, color, size="sm"), unsafe_allow_html=True)
                st.metric(label, value)

    st.write("")
    render_risk_banner(trend["risk"], trend["recommendation"])

    if trend["has_data"]:
        df = pd.DataFrame({"date": trend["days"], "avg_score": trend["daily_avg"]}).set_index("date")
        head_col, pill_col = st.columns([3, 1])
        head_col.subheader("21-day cognitive engagement trend")
        with pill_col:
            st.write("")
            render_trend_pill(trend["trend"])
        with st.container(border=True):
            st.line_chart(df, color="#146356")

    st.subheader("Game-by-game breakdown (last 21 days)")
    rows = []
    for gtype, glabel in GAME_TYPES.items():
        g_scores = db.get_scores(patient["id"], gtype)
        if g_scores:
            avg = sum(r["score"] for r in g_scores) / len(g_scores)
            rows.append({"Game": glabel, "Sessions": len(g_scores), "Average score": round(avg, 1)})
    if rows:
        with st.container(border=True):
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No game sessions logged yet for this profile.")

    st.subheader("Today's reminders")
    for r in reminders_today:
        with st.container(border=True):
            rc1, rc2 = st.columns([0.14, 0.86])
            with rc1:
                st.markdown(icon_badge_html(r["icon"] or "📌", "var(--ss-gold)", size="sm"), unsafe_allow_html=True)
            with rc2:
                status = "Done ✅" if r["done"] else "Pending ⏳"
                st.markdown(f"**{r['time_str']}** — {r['task']}  \n_{r['type']} · {status}_")
    render_add_reminder_form(patient["id"], key_suffix="caregiver")

    st.info("🌐 Interface supports English, Assamese, Khasi, Bodo, Manipuri and Mizo — "
            "built for accessibility across the North Eastern Region. Non-English labels beyond "
            "Assamese are draft translations pending native-speaker review.")

# ============================================================= PATIENT ===
else:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1.1rem;">
            <div class="ss-badge ss-badge-sm"
                 style="background:linear-gradient(135deg,#eaf3ee,#f1e9fb);border:2px solid var(--ss-primary);">🪔</div>
            <div>
                <div style="font-family:'Poppins',sans-serif;font-weight:800;font-size:1.35rem;
                            color:var(--ss-primary-dark);line-height:1.15;">{L('app')}</div>
                <div style="font-size:0.82rem;color:var(--ss-text-muted);">{L('sub')}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------------------------------------------- home
    if ss.page == "home":
        reminders_today = db.get_reminders(patient["id"])
        done_count = sum(1 for r in reminders_today if r["done"])
        total = max(len(reminders_today), 1)
        pct = round(100 * done_count / total)

        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:1rem;">
                {icon_badge_html('☀️', 'linear-gradient(135deg,var(--ss-gold),var(--ss-accent-dark))')}
                <div style="font-family:'Poppins',sans-serif;font-weight:800;font-size:1.5rem;
                            color:var(--ss-primary-dark);">{L('greeting')}, {patient['name']}</div>
            </div>
            <div style="background:var(--ss-card);border:1px solid rgba(20,99,86,0.1);border-radius:16px;
                        padding:1rem 1.2rem;box-shadow:0 6px 16px rgba(20,99,86,0.08);margin-bottom:1.3rem;">
                <div style="display:flex;justify-content:space-between;font-size:0.85rem;
                            color:var(--ss-text-muted);margin-bottom:0.4rem;">
                    <span>Memory leaves today</span><span>{done_count} of {total}</span>
                </div>
                <div style="background:var(--ss-bg-alt);border-radius:999px;height:14px;overflow:hidden;">
                    <div style="width:{pct}%;height:100%;border-radius:999px;
                                background:linear-gradient(90deg,var(--ss-primary),var(--ss-primary-light));
                                transition:width 0.6s ease;"></div>
                </div>
                <div style="margin-top:0.5rem;font-size:1.1rem;letter-spacing:0.1em;">
                    {"🍃" * done_count}{"🍂" * (total - done_count)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pending = total - done_count
        t1, t2 = st.columns(2)
        with t1:
            render_tile("🧩", "linear-gradient(135deg,var(--ss-primary),var(--ss-primary-light))",
                        L("games"), "Gentle daily play", "Open", "tile_games", "games_menu")
        with t2:
            render_tile("🖼️", "linear-gradient(135deg,var(--ss-secondary),var(--ss-secondary-dark))",
                        L("box"), "Familiar faces & notes", "Open", "tile_box", "memory_box")
        t3, t4 = st.columns(2)
        with t3:
            sub = f"{pending} pending" if pending else "All done today"
            render_tile("⏰", "linear-gradient(135deg,var(--ss-gold),var(--ss-accent-dark))",
                        L("reminders"), sub, "Open", "tile_reminders", "reminders")
        with t4:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                        {icon_badge_html('📞', 'linear-gradient(135deg,var(--ss-accent),var(--ss-accent-dark))')}
                        <div>
                            <div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-dark);">{L('call')}</div>
                            <div style="font-size:0.85rem;color:var(--ss-text-muted);">Priya Bora, Daughter</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Call now", key="tile_call", use_container_width=True):
                    st.toast("📞 Calling Priya Bora (Daughter)...")

    # ---------------------------------------------------------- games menu
    elif ss.page == "games_menu":
        if st.button("← Back"):
            goto("home")
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:1rem;">
                {icon_badge_html('🧠', 'linear-gradient(135deg,var(--ss-primary),var(--ss-primary-light))')}
                <div style="font-family:'Poppins',sans-serif;font-weight:800;font-size:1.5rem;
                            color:var(--ss-primary-dark);">Memory Games</div></div>""",
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                    {icon_badge_html('🃏', 'linear-gradient(135deg,var(--ss-primary),var(--ss-primary-light))')}
                    <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-dark);">Memory Match</div>
                    <div style="font-size:0.85rem;color:var(--ss-text-muted);">Flip cards and find matching pairs</div></div>
                    </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Play", key="tile_mm", use_container_width=True):
                for k in list(ss.keys()):
                    if k.startswith("mm_"):
                        del ss[k]
                deck = SYMBOLS * 2
                random.shuffle(deck)
                ss.mm_deck = [{"symbol": s, "matched": False} for s in deck]
                ss.mm_flipped, ss.mm_moves, ss.mm_pending, ss.mm_logged = [], 0, False, False
                goto("game_memory")

        with st.container(border=True):
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                    {icon_badge_html('🎨', 'linear-gradient(135deg,var(--ss-secondary),var(--ss-secondary-dark))')}
                    <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-dark);">Pattern Recall</div>
                    <div style="font-size:0.85rem;color:var(--ss-text-muted);">Watch and repeat a sequence</div></div>
                    </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Play", key="tile_pr", use_container_width=True):
                ss.pr_sequence, ss.pr_phase, ss.pr_round, ss.pr_user_pos, ss.pr_best = [], "ready", 0, 0, 0
                goto("game_pattern")

        with st.container(border=True):
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                    {icon_badge_html('👪', 'linear-gradient(135deg,var(--ss-gold),var(--ss-accent-dark))')}
                    <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-dark);">Who Is This?</div>
                    <div style="font-size:0.85rem;color:var(--ss-text-muted);">Gentle family recognition practice</div></div>
                    </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Play", key="tile_fm", use_container_width=True):
                family = db.get_family(patient["id"])
                if len(family) < 3:
                    st.warning("Add at least 3 people to Memory Box first to unlock this game.")
                else:
                    queue = list(family)
                    random.shuffle(queue)
                    ss.fm_queue, ss.fm_index, ss.fm_answered, ss.fm_chosen, ss.fm_correct = queue, 0, False, None, 0
                    goto("game_family")

    # ------------------------------------------------------- memory match
    elif ss.page == "game_memory":
        if st.button("← Back to games"):
            goto("games_menu")
        st.header("Memory Match")
        st.caption("Tap two cards to find matching pairs. There is no timer — take your time.")

        deck = ss.mm_deck
        cols = st.columns(4)
        for i, card in enumerate(deck):
            with cols[i % 4]:
                shown = card["matched"] or i in ss.mm_flipped
                label = card["symbol"] if shown else "❔"
                disabled = card["matched"] or i in ss.mm_flipped or (len(ss.mm_flipped) == 2)
                if st.button(label, key=f"mm_{i}", use_container_width=True, disabled=disabled):
                    ss.mm_flipped.append(i)
                    if len(ss.mm_flipped) == 2:
                        ss.mm_moves += 1
                        a, b = ss.mm_flipped
                        if deck[a]["symbol"] == deck[b]["symbol"]:
                            deck[a]["matched"] = True
                            deck[b]["matched"] = True
                            ss.mm_flipped = []
                        else:
                            ss.mm_pending = True
                    st.rerun()

        matched_pairs = sum(1 for c in deck if c["matched"]) // 2
        st.write(f"Moves: {ss.mm_moves} | Pairs found: {matched_pairs} / 6")

        if ss.mm_pending:
            st.info("Not a match this time — that's alright, take another look.")
            if st.button("Next"):
                ss.mm_flipped = []
                ss.mm_pending = False
                st.rerun()

        if matched_pairs == 6:
            score = max(20, 100 - (ss.mm_moves - 6) * 5)
            st.success(f"🎉 Wonderful! All pairs matched in {ss.mm_moves} moves. A memory leaf just grew!")
            if not ss.mm_logged:
                db.log_game_score(patient["id"], "memory_match", score)
                ss.mm_logged = True
            if st.button("Play again"):
                deck2 = SYMBOLS * 2
                random.shuffle(deck2)
                ss.mm_deck = [{"symbol": s, "matched": False} for s in deck2]
                ss.mm_flipped, ss.mm_moves, ss.mm_pending, ss.mm_logged = [], 0, False, False
                st.rerun()

    # ------------------------------------------------------- pattern game
    elif ss.page == "game_pattern":
        if st.button("← Back to games"):
            goto("games_menu")
        st.header("Pattern Recall")

        if ss.pr_phase == "ready":
            st.caption("Watch the pattern, then repeat it back in the same order.")
            if st.button("Start"):
                ss.pr_round = 1
                ss.pr_sequence = [random.randint(0, 3)]
                ss.pr_phase = "showing"
                st.rerun()

        elif ss.pr_phase == "showing":
            sequence_text = " → ".join(PADS[i] for i in ss.pr_sequence)
            st.info(f"**Pattern:** {sequence_text}")
            st.caption(f"Round {ss.pr_round} · Best so far: {ss.pr_best}")
            if st.button("I've memorised it — let me repeat it"):
                ss.pr_user_pos = 0
                ss.pr_phase = "input"
                st.rerun()

        elif ss.pr_phase == "input":
            st.caption(f"Tap the panels in the order shown · Round {ss.pr_round}")
            cols = st.columns(2)
            for i, pad in enumerate(PADS):
                with cols[i % 2]:
                    if st.button(pad, key=f"pad_{i}", use_container_width=True):
                        if ss.pr_sequence[ss.pr_user_pos] == i:
                            ss.pr_user_pos += 1
                            if ss.pr_user_pos == len(ss.pr_sequence):
                                ss.pr_best = max(ss.pr_best, ss.pr_round)
                                ss.pr_round += 1
                                ss.pr_sequence.append(random.randint(0, 3))
                                ss.pr_phase = "showing"
                        else:
                            score = min(100, ss.pr_best * 15)
                            if ss.pr_best > 0:
                                db.log_game_score(patient["id"], "pattern_recall", score)
                            st.session_state["pr_msg"] = "That's alright — let's begin again gently."
                            ss.pr_sequence, ss.pr_phase, ss.pr_round, ss.pr_user_pos = [], "ready", 0, 0
                        st.rerun()
            if ss.get("pr_msg"):
                st.warning(ss.pop("pr_msg"))

    # -------------------------------------------------------- family game
    elif ss.page == "game_family":
        if st.button("← Back to games"):
            goto("games_menu")
        st.header("Who Is This?")

        queue = ss.fm_queue
        if ss.fm_index >= len(queue):
            score = round(100 * ss.fm_correct / len(queue))
            st.success(f"🎉 Round complete — {ss.fm_correct} of {len(queue)} remembered.")
            if not ss.get("fm_logged"):
                db.log_game_score(patient["id"], "family_match", score)
                ss.fm_logged = True
            if st.button("Play again"):
                random.shuffle(queue)
                ss.fm_index, ss.fm_answered, ss.fm_chosen, ss.fm_correct, ss.fm_logged = 0, False, None, 0, False
                st.rerun()
        else:
            person = queue[ss.fm_index]
            st.markdown(
                f"""
                <div style="display:flex;justify-content:center;margin:0.6rem 0 1rem;">
                    <div style="width:6rem;height:6rem;border-radius:999px;display:flex;align-items:center;
                                justify-content:center;font-family:'Poppins',sans-serif;font-weight:700;
                                font-size:2rem;color:var(--ss-primary-dark);
                                background:linear-gradient(135deg,#eaf3ee 0%,#f1e9fb 100%);
                                border:3px solid var(--ss-primary);box-shadow:0 8px 20px rgba(20,99,86,0.18);">
                        {person['initials']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write(f"Relation clue: **your {person['relation']}**")

            if "fm_choices" not in ss or ss.get("fm_choices_idx") != ss.fm_index:
                others = [f["name"] for f in queue if f["name"] != person["name"]]
                random.shuffle(others)
                choices = [person["name"]] + others[:2]
                random.shuffle(choices)
                ss.fm_choices = choices
                ss.fm_choices_idx = ss.fm_index

            for name in ss.fm_choices:
                if st.button(name, key=f"fm_choice_{ss.fm_index}_{name}", disabled=ss.fm_answered):
                    ss.fm_answered = True
                    ss.fm_chosen = name
                    if name == person["name"]:
                        ss.fm_correct += 1
                    st.rerun()

            if ss.fm_answered:
                correct = ss.fm_chosen == person["name"]
                prefix = "✅ Yes, that's right!" if correct else "💛 That's okay — this is"
                st.info(f"{prefix} **{person['name']}**, your {person['relation'].lower()}. {person['note']}")
                if st.button("Continue"):
                    ss.fm_index += 1
                    ss.fm_answered = False
                    ss.fm_chosen = None
                    st.rerun()

    # --------------------------------------------------------- memory box
    elif ss.page == "memory_box":
        if st.button("← Back"):
            goto("home")
        st.header(L("box"))
        family = db.get_family(patient["id"])
        cols = st.columns(2)
        for i, p in enumerate(family):
            with cols[i % 2]:
                with st.container(border=True):
                    st.markdown(
                        f"""<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.4rem;">
                            {avatar_html(p['initials'])}
                            <div><div style="font-weight:700;color:var(--ss-primary-dark);">{p['name']}</div>
                            <div style="font-size:0.8rem;color:var(--ss-text-muted);">{p['relation']} &middot; {p['last_contact']}</div>
                            </div></div>""",
                        unsafe_allow_html=True,
                    )
                    st.write(p["note"])
                    speak_button(f"Message from {p['name']}, your {p['relation']}. {p['note']}", key=f"voice_{p['id']}")

        with st.expander("+ Add a family memory"):
            with st.form("add_person_form", clear_on_submit=True):
                name = st.text_input("Name")
                relation = st.text_input("Relation (e.g. Son, Neighbour)")
                note = st.text_area("A short note to help remember them", "")
                if st.form_submit_button("Save to Memory Box"):
                    if name and relation:
                        db.add_family_member(patient["id"], name, relation, note)
                        st.success("Saved to Memory Box 💛")
                        st.rerun()
                    else:
                        st.warning("Please enter both a name and relation.")

    # ---------------------------------------------------------- reminders
    elif ss.page == "reminders":
        if st.button("← Back"):
            goto("home")
        st.header(L("reminders"))
        reminders_today = db.get_reminders(patient["id"])
        for r in reminders_today:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{r['time_str']}** — {r['icon']} {r['task']}  \n_{r['type']}_")
                checked = c2.checkbox("Done", value=bool(r["done"]), key=f"rem_{r['id']}")
                if checked != bool(r["done"]):
                    db.set_reminder_done(r["id"], checked)
                    st.rerun()
                with c3:
                    speak_button(r["task"], key=f"speak_rem_{r['id']}")

        render_add_reminder_form(patient["id"], key_suffix="patient")
