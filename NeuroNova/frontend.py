"""
frontend.py — all Streamlit UI/rendering code for Neuronova.

Every screen, layout, style and navigation flow the user sees lives here.
db.py, cognitive_ai.py and voice.py stay backend-only (data, analytics, speech);
app.py is just the entry point that wires the database up and calls run().
"""

import base64
import os
import random
from datetime import datetime
import streamlit as st
import pandas as pd

import db
import cognitive_ai
import voice
import report

# NOTE on translation quality: "en" and "as" (Assamese) are solid. The "kha"
# (Khasi), "brx" (Bodo), "mni" (Manipuri/Meitei) and "lus" (Mizo) entries
# below are AI best-effort drafts, NOT verified by native speakers — treat
# them as placeholders to be reviewed before real patient-facing use.
LABELS = {
    "en": {"app": "Neuronova", "sub": "Memory Companion · North Eastern Region",
           "greeting": {"morning": "Good Morning", "afternoon": "Good Afternoon",
                        "evening": "Good Evening", "night": "Good Night"},
           "games": "Play Memory Games", "box": "My Memory Box",
           "reminders": "Today's Reminders"},
    "as": {"app": "Neuronova", "sub": "মেমোৰি কম্পেনিয়ন · উত্তৰ পূৰ্বাঞ্চল",
           "greeting": {"morning": "শুভ প্ৰভাত", "afternoon": "শুভ অপৰাহ্ণ",
                        "evening": "শুভ সন্ধিয়া", "night": "শুভ ৰাতি"},
           "games": "স্মৃতি খেল", "box": "মোৰ স্মৃতি বাকচ",
           "reminders": "আজিৰ মনত পেলোৱা"},
    "kha": {"app": "Neuronova", "sub": "Nongïarap Kynmaw · Ri Khasi–Jaiñtia",
            "greeting": {"morning": "Mih Shaphrang", "afternoon": "Mih Sngiap",
                         "evening": "Mih Mynstep", "night": "Mih Tarim"},
            "games": "Khena Kynmaw", "box": "Ka Bokso Kynmaw Jong Nga",
            "reminders": "Ka Kynmaw Mynta"},
    "brx": {"app": "Neuronova", "sub": "सोदोबनायाव फुंखा · बर'लैंड",
            "greeting": {"morning": "गुबुन सान", "afternoon": "गुबुन मदैनि",
                         "evening": "गुबुन बेला", "night": "गुबुन आबेन्दो"},
            "games": "सोदोब आन्जोरनाय गेम", "box": "आं'नि सोदोब बाक्सा",
            "reminders": "दिनैनि खोन्दोब"},
    "mni": {"app": "Neuronova", "sub": "মৈতৈলোন্ · মণিপুর",
            "greeting": {"morning": "নুংঙাইবা য়েংথোক্কী", "afternoon": "নুংঙাইবা নুমিৎ",
                         "evening": "নুংঙাইবা নুংথিল", "night": "নুংঙাইবা অহিং"},
            "games": "নীংশিং খেল থাগৎপা", "box": "ঐগী নীংশিং বক্স",
            "reminders": "ঙসিগী ৱারোল"},
    "lus": {"app": "Neuronova", "sub": "Hriatna Ṭhian · Zoram",
            "greeting": {"morning": "Chibai", "afternoon": "Chibai",
                         "evening": "Chibai", "night": "Chibai"},
            "games": "Hriatna Inen", "box": "Ka Hriatna Bâwm",
            "reminders": "Tunlaia Hriattîrna"},
}

GAME_TYPES = {"memory_match": "Memory Match", "pattern_recall": "Pattern Recall", "traditions_match": "Know Your Roots"}
SYMBOLS = ["🍵", "🐘", "🛶", "🥁", "🌾", "🎭", "🦚", "🌸"]
PADS = ["Tea Garden", "Muga Silk", "River Boat", "Bihu Drum", "Bamboo Grove", "Hornbill Dance"]

DIFFICULTIES = ["Easy", "Medium", "Hard"]
MM_PAIRS = {"Easy": 3, "Medium": 6, "Hard": 8}
PR_PADS = {"Easy": 2, "Medium": 4, "Hard": 6}
# Know Your Roots doesn't scale with the shared difficulty level -- each
# state's curated set is intentionally small (3 items), so "harder" would
# just mean re-showing the same pool with no real change. Always offer up
# to this many choices instead.
TM_FIXED_CHOICES = 4

ss = st.session_state


# ------------------------------------------------------------------ helpers --

def goto(page):
    ss.page = page
    st.rerun()


def L(key):
    return LABELS[ss.lang][key]


def greeting_period():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def time_greeting():
    period = greeting_period()
    emoji = {"morning": "☀️", "afternoon": "🌤️", "evening": "🌆", "night": "🌙"}[period]
    return LABELS["en"]["greeting"][period], emoji


def current_patient(patients):
    return next(p for p in patients if p["id"] == ss.patient_id)


def adjust_difficulty(score, patient_id):
    """ML-driven difficulty adjustment: combines the just-finished session's
    score (0-100, the same score already logged to game_scores) with the
    patient's longer-term trend from cognitive_ai.analyze_trend() -- the
    same least-squares regression over score history that powers the
    caregiver dashboard's trend chart. Using the fitted slope (not just one
    session in isolation) means a single lucky or unlucky session can't
    override an established trend, and a level-up requires genuine,
    sustained improvement rather than one easy round.

    Criterion: score >= 80 AND the trend isn't declining steps up one level
    (Easy -> Medium -> Hard). score <= 40 OR a clearly declining trend
    (slope <= -1.5, the same threshold analyze_trend uses for "High risk")
    steps down one level. Already-Hard sessions can't step up further, and
    already-Easy sessions can't step down further.

    Returns "up", "down", or None (no change) so callers can tell the
    patient what happened and why.
    """
    idx = DIFFICULTIES.index(ss.difficulty)
    trend = cognitive_ai.analyze_trend(db.get_scores(patient_id, days=21))
    slope = trend["slope_per_day"] if trend["has_data"] else 0.0

    if score >= 80 and slope >= -0.3 and idx < len(DIFFICULTIES) - 1:
        ss.difficulty = DIFFICULTIES[idx + 1]
        return "up"
    if (score <= 40 or slope <= -1.5) and idx > 0:
        ss.difficulty = DIFFICULTIES[idx - 1]
        return "down"
    return None


def speak_button(text, key):
    if st.button("🔊 Play aloud", key=key):
        if voice.is_available():
            path = voice.speak_to_file(text)
            if path:
                st.audio(path, autoplay=True)
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
                "Type", ["Medicine", "Hydration", "Meal", "Activity", "Appointment", "Family", "Custom"],
                key=f"rem_type_{key_suffix}"
            )
            if st.form_submit_button("Save reminder"):
                if time_str and task:
                    icon = {
                        "Medicine": "💊", "Hydration": "💧", "Meal": "🍚", "Activity": "🧩",
                        "Appointment": "🩺", "Family": "📞", "Custom": "📌",
                    }[rtype]
                    db.add_reminder(patient_id, time_str, task, rtype, icon)
                    st.success("Reminder added")
                    st.rerun()
                else:
                    st.warning("Please enter both a time and a task.")


def icon_badge_html(emoji, bg, size="md"):
    cls = "ss-badge" if size == "md" else "ss-badge ss-badge-sm"
    return f'<div class="{cls}" style="background:{bg};">{emoji}</div>'


def _photo_data_uri(photo_path):
    """Base64-encode a photo so it can be embedded directly in the raw HTML
    cards this app builds (a plain <img src="local/path"> won't resolve in
    the browser, since these aren't served as static files)."""
    if not photo_path:
        return None
    full_path = os.path.join(os.path.dirname(__file__), photo_path)
    if not os.path.exists(full_path):
        return None
    ext = os.path.splitext(full_path)[1].lstrip(".").lower() or "png"
    with open(full_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    return f"data:image/{ext};base64,{encoded}"


def avatar_html(initials, photo_path=None, size_rem=2.6):
    uri = _photo_data_uri(photo_path)
    if uri:
        return (
            f'<img src="{uri}" class="ss-avatar" '
            f'style="width:{size_rem}rem;height:{size_rem}rem;object-fit:cover;" />'
        )
    return f'<div class="ss-avatar" style="width:{size_rem}rem;height:{size_rem}rem;">{initials}</div>'


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
        "High": ("var(--ss-risk-high)", "rgba(255,59,92,0.12)", "⚠️"),
        "Medium": ("var(--ss-risk-medium)", "rgba(255,180,0,0.12)", "🔶"),
        "Low": ("var(--ss-risk-low)", "rgba(36,242,160,0.12)", "✅"),
        "Unknown": ("var(--ss-text-muted)", "rgba(147,164,201,0.1)", "ℹ️"),
    }
    color, bg, icon = tone.get(risk, tone["Unknown"])
    st.markdown(
        f"""
        <div style="background:{bg};border-left:6px solid {color};border-radius:14px;
                    padding:1.1rem 1.3rem;display:flex;gap:0.9rem;align-items:flex-start;
                    backdrop-filter:blur(14px);box-shadow:0 3px 12px rgba(31,51,47,0.10);margin-bottom:1rem;">
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
        "Improving": ("var(--ss-risk-low)", "rgba(36,242,160,0.12)", "📈"),
        "Stable": ("var(--ss-primary-dark)", "rgba(62,142,133,0.15)", "➖"),
        "Declining": ("var(--ss-risk-high)", "rgba(255,59,92,0.12)", "📉"),
    }
    color, bg, icon = tone.get(trend, ("var(--ss-text-muted)", "rgba(147,164,201,0.1)", "❔"))
    st.markdown(
        f"""<span style="background:{bg};color:{color};border:1.5px solid {color};
              border-radius:999px;padding:0.25rem 0.8rem;font-weight:700;font-size:0.85rem;
              display:inline-flex;align-items:center;gap:0.35rem;">{icon} {trend}</span>""",
        unsafe_allow_html=True,
    )


def inject_global_css():
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    with open(css_path, encoding="utf-8") as f:
        st.markdown(f"<style>\n{f.read()}\n</style>", unsafe_allow_html=True)


def render_welcome():
    greeting, emoji = time_greeting()
    st.write("")
    st.write("")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(
            f"""
            <div class="ss-welcome-card">
                <div class="ss-welcome-orb">{emoji}</div>
                <h1>{greeting}</h1>
                <p class="ss-welcome-sub">Welcome to Neuronova, your gentle memory companion.
                    Tap below whenever you're ready to begin.</p>
                <div class="ss-welcome-chips">
                    <span class="ss-chip">🔒 Private &amp; secure</span>
                    <span class="ss-chip">🌐 6 regional languages</span>
                    <span class="ss-chip">💙 Made for elder care</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("✨  Enter Neuronova", use_container_width=True):
            ss.page = "landing"
            st.rerun()
        st.caption("SIH26003 — working prototype")


def render_landing():
    if st.button("← Back"):
        ss.page = "welcome"
        st.rerun()

    chips = "".join(f'<span class="ss-chip">{name}</span>' for name in db.LANGUAGES.values())
    st.markdown(
        f"""
        <div class="ss-hero">
            <span class="ss-diya">🧠</span>
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
            ss.page = "login"
            st.rerun()
    st.caption("SIH26003 — working prototype")


def render_login(patients):
    if st.button("← Back"):
        ss.page = "landing"
        st.rerun()

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(
            """
            <div class="ss-welcome-card">
                <div class="ss-welcome-orb">🔐</div>
                <h1>Sign In</h1>
                <p class="ss-welcome-sub">Enter the patient's name and PIN to continue.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")

        patient_names = [p["name"] for p in patients]
        with st.form("login_form"):
            name = st.selectbox("Patient name", patient_names)
            pin = st.text_input("PIN", type="password", max_chars=6)
            role_choice = st.radio(
                "Continue as", ["Patient", "Caregiver"], horizontal=True
            )
            submitted = st.form_submit_button("Enter", use_container_width=True)

        if submitted:
            patient = next(p for p in patients if p["name"] == name)
            if db.verify_patient_pin(patient, pin):
                ss.patient_id = patient["id"]
                ss.role = role_choice
                if patient["language"] in LABELS:
                    ss.lang = patient["language"]
                ss.page = "home"
                st.rerun()
            else:
                st.error("Incorrect PIN. Please try again.")

        with st.expander("Forgot PIN?"):
            st.caption(
                "Offline PIN reset — no email or SMS needed. Enter the "
                "caregiver's admin PIN to generate a new PIN for a patient."
            )
            with st.form("forgot_pin_form"):
                forgot_name = st.selectbox("Patient name", patient_names, key="forgot_pin_name")
                admin_pin = st.text_input("Caregiver admin PIN", type="password", max_chars=6)
                reset_submitted = st.form_submit_button("Reset PIN")
            if reset_submitted:
                if db.verify_admin_pin(admin_pin):
                    forgot_patient = next(p for p in patients if p["name"] == forgot_name)
                    new_pin = db.reset_patient_pin(forgot_patient["id"])
                    st.success(f"New PIN for {forgot_name}: **{new_pin}** — write this down, it won't be shown again.")
                else:
                    st.error("Incorrect admin PIN.")

        with st.expander("+ Register a new patient"):
            with st.form("add_patient_form", clear_on_submit=True):
                new_name = st.text_input("Patient's full name")
                new_age = st.number_input("Age", min_value=1, max_value=120, value=70)
                new_village = st.text_input("Village / town")
                lang_codes = list(LABELS.keys())
                new_lang = st.selectbox(
                    "Preferred language (for reading the app)", lang_codes,
                    format_func=lambda c: db.LANGUAGES.get(c, c),
                    key="add_patient_lang",
                )
                state_codes = list(db.STATES.keys())
                new_state = st.selectbox(
                    "State (for 'Know Your Roots' — independent of language above)",
                    state_codes,
                    format_func=lambda c: db.STATES.get(c, c),
                    key="add_patient_state",
                    help="Determines which state's culture shows in the memory game — "
                         "not tied to the language chosen above, since someone can prefer "
                         "reading in English while still being from, say, Nagaland.",
                )
                new_pin = st.text_input("Set a PIN (4-6 digits)", type="password", max_chars=6)
                add_submitted = st.form_submit_button("Register patient", use_container_width=True)
            if add_submitted:
                if new_name and new_village and new_pin and new_pin.isdigit() and 4 <= len(new_pin) <= 6:
                    db.add_patient(new_name, int(new_age), new_village, new_lang, new_state, new_pin)
                    st.success(f"{new_name} registered — select their name above to sign in.")
                    st.rerun()
                else:
                    st.warning("Please enter a name, village, and a 4-6 digit PIN.")


def render_patient_photo_editor(patient):
    """Photo upload/preview/remove controls for the current patient. Lives in
    the sidebar (caregiver mode only) so it's reachable from any page."""
    with st.expander("📷 Update patient's photo"):
        new_photo = st.file_uploader(
            "Photo (jpg/png)", type=["jpg", "jpeg", "png"], key="patient_photo_upload"
        )
        if new_photo is not None:
            st.image(new_photo, width=110, caption="Preview")

        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("Save photo", key="save_patient_photo",
                          disabled=new_photo is None, use_container_width=True):
                try:
                    photo_path = db.save_uploaded_photo(new_photo.getvalue(), new_photo.name)
                except ValueError as e:
                    st.error(str(e))
                else:
                    db.update_patient_photo(patient["id"], photo_path)
                    st.success("Patient photo updated.")
                    st.rerun()
        with bcol2:
            if st.button("Remove photo", key="remove_patient_photo",
                          disabled=not patient["photo_path"], use_container_width=True):
                db.update_patient_photo(patient["id"], None)
                st.success("Photo removed.")
                st.rerun()


def render_sidebar(patients):
    with st.sidebar:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.6rem;">
                <div class="ss-badge ss-badge-sm"
                     style="background:linear-gradient(135deg,var(--ss-primary-light),var(--ss-primary));border:2px solid var(--ss-primary-dark);box-shadow:0 4px 10px rgba(31,51,47,0.2);">🧠</div>
                <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.3rem;color:var(--ss-primary-dark);">
                    Neuronova</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        patient = current_patient(patients)
        initials = "".join(w[0] for w in patient["name"].split()[:2]).upper()
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.7rem;background:var(--ss-card);
                        border:1px solid rgba(31,51,47,0.10);border-radius:14px;padding:0.7rem 0.9rem;
                        margin:0.5rem 0 0.9rem;box-shadow:0 4px 12px rgba(31,51,47,0.08);">
                {avatar_html(initials, patient['photo_path'])}
                <div>
                    <div style="font-weight:700;color:var(--ss-primary-dark);">{patient['name']}</div>
                    <div style="font-size:0.8rem;color:var(--ss-text-muted);">{db.patient_location(patient)} &middot; age {patient['age']}
                        &middot; signed in as {ss.role}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if ss.role == "Caregiver":
            render_patient_photo_editor(patient)

        lang_codes = list(LABELS.keys())
        ss.lang = st.selectbox(
            "Language", lang_codes, index=lang_codes.index(ss.lang),
            format_func=lambda c: db.LANGUAGES.get(c, c),
        )

        if st.button("🚪 Log out", use_container_width=True):
            ss.page = "login"
            st.rerun()
        st.caption("SIH26003 — working prototype")


def render_caregiver(patient):
    is_caregiver = ss.role == "Caregiver"
    if not is_caregiver:
        st.caption("👀 Read-only family view — ask the caregiver to add or edit entries.")
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.3rem;">
            {icon_badge_html('📊', 'linear-gradient(135deg,var(--ss-secondary),var(--ss-secondary-dark))')}
            <div>
                <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.7rem;
                            color:var(--ss-primary-dark);line-height:1.1;">Caregiver Dashboard</div>
                <div style="color:var(--ss-text-muted);">
                    Monitoring <b style="color:var(--ss-text);">{patient['name']}</b>,
                    age {patient['age']} &middot; {db.patient_location(patient)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.download_button(
        "📄 Download PDF report for doctor / PHC visit",
        data=report.generate_caregiver_report(patient),
        file_name=f"neuronova_report_{patient['name'].replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        key="download_pdf_report",
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
        (c3, "💊", "var(--ss-accent-dark)", "Medicine adherence today",
         f"{meds_done}/{meds_total} ({adherence_pct:.0f}%)" if meds_total else "—"),
    ]
    for col, emoji, color, label, value in metric_specs:
        with col:
            with st.container(border=True):
                st.markdown(icon_badge_html(emoji, color, size="sm"), unsafe_allow_html=True)
                st.metric(label, value)

    st.write("")
    render_risk_banner(trend["risk"], trend["recommendation"])

    range_options = {"24 Hours": 1, "7 Days": 7, "15 Days": 15}
    range_choice = st.radio(
        "Chart range", list(range_options.keys()), index=1, horizontal=True, key="trend_range"
    )

    if range_choice == "24 Hours":
        recent_scores = db.get_scores(patient["id"], days=1)
        st.subheader("Last 24 hours — session scores")
        if recent_scores:
            df = pd.DataFrame({
                "time": pd.to_datetime([r["played_at"] for r in recent_scores]),
                "score": [r["score"] for r in recent_scores],
            }).set_index("time").sort_index()
            with st.container(border=True):
                st.line_chart(df, color="#2C6B64")
        else:
            st.info("No game sessions logged in the last 24 hours.")
    else:
        ranged_trend = cognitive_ai.analyze_trend(db.get_scores(patient["id"], days=range_options[range_choice]))
        head_col, pill_col = st.columns([3, 1])
        head_col.subheader(f"{range_choice} cognitive engagement trend")
        if ranged_trend["has_data"]:
            with pill_col:
                st.write("")
                render_trend_pill(ranged_trend["trend"])
            df = pd.DataFrame(
                {"date": ranged_trend["days"], "avg_score": ranged_trend["daily_avg"]}
            ).set_index("date")
            with st.container(border=True):
                st.line_chart(df, color="#2C6B64")
        else:
            st.info(f"Not enough data yet for a {range_choice.lower()} trend.")

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
    if is_caregiver:
        render_add_reminder_form(patient["id"], key_suffix="caregiver")

    st.subheader("Family & Memory Box")
    render_family_gallery(patient, key_suffix="caregiver", editable=is_caregiver)

    st.subheader("Traditions & Culture Gallery")
    st.caption("Curate the North East festivals, dance, attire, food and crafts used in the 'Know Your Roots' game.")
    render_traditions_gallery(key_suffix="caregiver", editable=is_caregiver)

    st.info("🌐 Interface supports English, Assamese, Khasi, Bodo, Manipuri and Mizo — "
            "built for accessibility across the North Eastern Region. Non-English labels beyond "
            "Assamese are draft translations pending native-speaker review.")


def render_patient_home(patient):
    reminders_today = db.get_reminders(patient["id"])
    done_count = sum(1 for r in reminders_today if r["done"])
    total = max(len(reminders_today), 1)
    pct = round(100 * done_count / total)

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:1rem;">
            {icon_badge_html('☀️', 'linear-gradient(135deg,var(--ss-gold),var(--ss-accent-dark))')}
            <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.5rem;
                        color:var(--ss-primary-dark);">{L('greeting')[greeting_period()]}, {patient['name']}</div>
        </div>
        <div style="background:var(--ss-card);border:1px solid rgba(31,51,47,0.10);border-radius:16px;
                    padding:1rem 1.2rem;box-shadow:0 6px 16px rgba(31,51,47,0.08);margin-bottom:1.3rem;">
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
    sub = f"{pending} pending" if pending else "All done today"
    render_tile("⏰", "linear-gradient(135deg,var(--ss-gold),var(--ss-accent-dark))",
                L("reminders"), sub, "Open", "tile_reminders", "reminders")


def render_games_menu(patient):
    if st.button("← Back"):
        goto("home")
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:1rem;">
            {icon_badge_html('🧠', 'linear-gradient(135deg,var(--ss-primary),var(--ss-primary-light))')}
            <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.5rem;
                        color:var(--ss-primary-dark);">Memory Games</div></div>""",
        unsafe_allow_html=True,
    )

    ss.setdefault("difficulty", "Medium")
    st.caption(
        f"Current difficulty: **{ss.difficulty}** — adjusts itself after every round, "
        "weighing both this session's score and the patient's longer-term trend "
        "(the same regression model behind the caregiver dashboard), so a single "
        "lucky or unlucky session can't override an established trend."
    )
    st.write("")

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
            pairs = MM_PAIRS[ss.difficulty]
            deck = SYMBOLS[:pairs] * 2
            random.shuffle(deck)
            ss.mm_deck = [{"symbol": s, "matched": False} for s in deck]
            ss.mm_pairs_target = pairs
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
            ss.pr_num_pads = PR_PADS[ss.difficulty]
            ss.pr_sequence, ss.pr_phase, ss.pr_round, ss.pr_user_pos, ss.pr_best = [], "ready", 0, 0, 0
            goto("game_pattern")

    with st.container(border=True):
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                {icon_badge_html('🪘', 'linear-gradient(135deg,var(--ss-gold),var(--ss-accent-dark))')}
                <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-dark);">Know Your Roots</div>
                <div style="font-size:0.85rem;color:var(--ss-text-muted);">Gentle practice with North East festivals, dance, attire & food</div></div>
                </div>""",
            unsafe_allow_html=True,
        )
        if st.button("Play", key="tile_tm", use_container_width=True):
            traditions = db.get_traditions_for_state(patient["state"])
            if len(traditions) < 3:
                state_label = db.STATES.get(patient["state"], "this patient's state")
                st.warning(
                    f"No {state_label} traditions yet — ask your caregiver to add at least 3 "
                    f"(with photos) for {state_label} in the caregiver dashboard to unlock this game. "
                    "Showing a different state's culture instead wouldn't be familiar to this patient."
                )
            else:
                queue = list(traditions)
                random.shuffle(queue)
                ss.tm_num_choices = min(TM_FIXED_CHOICES, len(traditions))
                ss.tm_queue, ss.tm_index, ss.tm_answered, ss.tm_chosen, ss.tm_correct = queue, 0, False, None, 0
                goto("game_traditions")


def render_game_memory(patient):
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

    pairs_target = ss.mm_pairs_target
    matched_pairs = sum(1 for c in deck if c["matched"]) // 2
    st.write(f"Moves: {ss.mm_moves} | Pairs found: {matched_pairs} / {pairs_target}")

    if ss.mm_pending:
        st.info("Not a match this time — that's alright, take another look.")
        if st.button("Next"):
            ss.mm_flipped = []
            ss.mm_pending = False
            st.rerun()

    if matched_pairs == pairs_target:
        score = max(20, 100 - (ss.mm_moves - pairs_target) * 5)
        st.success(f"🎉 Wonderful! All pairs matched in {ss.mm_moves} moves. A memory leaf just grew!")
        if not ss.mm_logged:
            db.log_game_score(patient["id"], "memory_match", score)
            ss.mm_logged = True
            change = adjust_difficulty(score, patient["id"])
            if change == "up":
                st.info(f"🔼 Score {score:.0f}% — that was easy! Moving up to **{ss.difficulty}** next round.")
            elif change == "down":
                st.info(f"🔽 Score {score:.0f}% — let's ease off to **{ss.difficulty}** next round.")
        if st.button("Play again"):
            new_pairs = MM_PAIRS[ss.difficulty]
            deck2 = SYMBOLS[:new_pairs] * 2
            random.shuffle(deck2)
            ss.mm_deck = [{"symbol": s, "matched": False} for s in deck2]
            ss.mm_pairs_target = new_pairs
            ss.mm_flipped, ss.mm_moves, ss.mm_pending, ss.mm_logged = [], 0, False, False
            st.rerun()


def render_game_pattern(patient):
    if st.button("← Back to games"):
        goto("games_menu")
    st.header("Pattern Recall")

    num_pads = ss.pr_num_pads

    if ss.pr_phase == "ready":
        st.caption("Watch the pattern, then repeat it back in the same order.")
        if st.button("Start"):
            ss.pr_round = 1
            ss.pr_sequence = [random.randint(0, num_pads - 1)]
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
        for i, pad in enumerate(PADS[:num_pads]):
            with cols[i % 2]:
                if st.button(pad, key=f"pad_{i}", use_container_width=True):
                    if ss.pr_sequence[ss.pr_user_pos] == i:
                        ss.pr_user_pos += 1
                        if ss.pr_user_pos == len(ss.pr_sequence):
                            ss.pr_best = max(ss.pr_best, ss.pr_round)
                            ss.pr_round += 1
                            ss.pr_sequence.append(random.randint(0, num_pads - 1))
                            ss.pr_phase = "showing"
                    else:
                        score = min(100, ss.pr_best * 15)
                        if ss.pr_best > 0:
                            db.log_game_score(patient["id"], "pattern_recall", score)
                        change = adjust_difficulty(score, patient["id"])
                        ss.pr_num_pads = PR_PADS[ss.difficulty]
                        if change == "up":
                            st.session_state["pr_msg"] = (
                                f"🔼 Reached round {ss.pr_best} — that was easy! "
                                f"Moving up to {ss.difficulty} next time."
                            )
                        elif change == "down":
                            st.session_state["pr_msg"] = f"🔽 Let's ease off to {ss.difficulty} next time — take it steady."
                        else:
                            st.session_state["pr_msg"] = "That's alright — let's begin again gently."
                        ss.pr_sequence, ss.pr_phase, ss.pr_round, ss.pr_user_pos = [], "ready", 0, 0
                    st.rerun()
        if ss.get("pr_msg"):
            st.warning(ss.pop("pr_msg"))


def render_game_traditions(patient):
    if st.button("← Back to games"):
        goto("games_menu")
    st.header("Know Your Roots")

    queue = ss.tm_queue
    if ss.tm_index >= len(queue):
        score = round(100 * ss.tm_correct / len(queue))
        st.success(f"🎉 Round complete — {ss.tm_correct} of {len(queue)} remembered.")
        if not ss.get("tm_logged"):
            db.log_game_score(patient["id"], "traditions_match", score)
            ss.tm_logged = True
        if st.button("Play again"):
            random.shuffle(queue)
            ss.tm_num_choices = min(TM_FIXED_CHOICES, len(queue))
            ss.tm_index, ss.tm_answered, ss.tm_chosen, ss.tm_correct, ss.tm_logged = 0, False, None, 0, False
            st.rerun()
    else:
        item = queue[ss.tm_index]
        photo_uri = _photo_data_uri(item['photo_path'])
        if photo_uri:
            face_html = (
                f'<img src="{photo_uri}" style="width:6rem;height:6rem;border-radius:999px;'
                f'object-fit:cover;border:3px solid var(--ss-primary-dark);'
                f'box-shadow:0 8px 20px rgba(31,51,47,0.2);" />'
            )
        else:
            initials = "".join(w[0] for w in item["name"].split()[:2]).upper()
            face_html = (
                f'<div style="width:6rem;height:6rem;border-radius:999px;display:flex;align-items:center;'
                f'justify-content:center;font-family:\'Exo 2\',sans-serif;font-weight:700;'
                f'font-size:2rem;color:#ffffff;'
                f'background:linear-gradient(135deg,var(--ss-primary-light) 0%,var(--ss-primary) 100%);'
                f'border:3px solid var(--ss-primary-dark);box-shadow:0 8px 20px rgba(31,51,47,0.2);">'
                f'{initials}</div>'
            )
        st.markdown(
            f"""
            <div style="display:flex;justify-content:center;margin:0.6rem 0 1rem;">
                {face_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write(f"Category clue: **{item['category']}**")

        if "tm_choices" not in ss or ss.get("tm_choices_idx") != ss.tm_index:
            others = [t["name"] for t in queue if t["name"] != item["name"]]
            random.shuffle(others)
            choices = [item["name"]] + others[: ss.tm_num_choices - 1]
            random.shuffle(choices)
            ss.tm_choices = choices
            ss.tm_choices_idx = ss.tm_index

        for name in ss.tm_choices:
            if st.button(name, key=f"tm_choice_{ss.tm_index}_{name}", disabled=ss.tm_answered):
                ss.tm_answered = True
                ss.tm_chosen = name
                if name == item["name"]:
                    ss.tm_correct += 1
                st.rerun()

        if ss.tm_answered:
            correct = ss.tm_chosen == item["name"]
            prefix = "✅ Yes, that's right!" if correct else "💛 That's okay — this is"
            st.info(f"{prefix} **{item['name']}** ({item['category']}). {item['note']}")
            if st.button("Continue"):
                ss.tm_index += 1
                ss.tm_answered = False
                ss.tm_chosen = None
                st.rerun()


def render_family_gallery(patient, key_suffix="", editable=True):
    """Shared family/memory-box gallery: photo + name + relation + note for
    each family member, plus a form to add a new one (with optional photo
    upload). Used on both the patient's Memory Box and the caregiver
    dashboard so either side can see and add real family photos. The
    add-form is hidden when editable=False (e.g. a read-only Family Member
    login on the caregiver dashboard)."""
    family = db.get_family(patient["id"])
    cols = st.columns(2)
    for i, p in enumerate(family):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(
                    f"""<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.4rem;">
                        {avatar_html(p['initials'], p['photo_path'])}
                        <div><div style="font-weight:700;color:var(--ss-primary-dark);">{p['name']}</div>
                        <div style="font-size:0.8rem;color:var(--ss-text-muted);">{p['relation']} &middot; {p['last_contact']}</div>
                        </div></div>""",
                    unsafe_allow_html=True,
                )
                st.write(p["note"])
                speak_button(
                    f"Message from {p['name']}, your {p['relation']}. {p['note']}",
                    key=f"voice_{key_suffix}_{p['id']}",
                )

    if editable:
        with st.expander("+ Add a family member (name & photo)"):
            with st.form(f"add_person_form_{key_suffix}", clear_on_submit=True):
                name = st.text_input("Name", key=f"fam_name_{key_suffix}")
                relation = st.text_input("Relation (e.g. Son, Neighbour)", key=f"fam_rel_{key_suffix}")
                note = st.text_area("A short note to help remember them", "", key=f"fam_note_{key_suffix}")
                photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png"], key=f"fam_photo_{key_suffix}")
                if st.form_submit_button("Save"):
                    if name and relation:
                        try:
                            photo_path = db.save_uploaded_photo(photo.getvalue(), photo.name) if photo else None
                        except ValueError as e:
                            st.error(str(e))
                        else:
                            db.add_family_member(patient["id"], name, relation, note, photo_path)
                            st.success("Saved 💛")
                            st.rerun()
                    else:
                        st.warning("Please enter both a name and relation.")


TRADITION_CATEGORIES = ["Festival", "Dance", "Attire", "Food", "Instrument", "Craft", "Other"]


def render_traditions_gallery(key_suffix="", editable=True):
    """Shared, patient-independent gallery of traditional North East items
    (festivals, dance, attire, food, crafts) with photo + name + note, plus
    a form to add a new one. Powers the 'Know Your Roots' game and is
    curated by caregivers rather than by patients. The add-form is hidden
    when editable=False (e.g. a read-only Family Member login)."""
    traditions = db.get_traditions()
    cols = st.columns(2)
    for i, t in enumerate(traditions):
        with cols[i % 2]:
            with st.container(border=True):
                initials = "".join(w[0] for w in t["name"].split()[:2]).upper()
                region = db.STATES.get(t["language"], "All states") if t["language"] else "All states"
                st.markdown(
                    f"""<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.4rem;">
                        {avatar_html(initials, t['photo_path'])}
                        <div><div style="font-weight:700;color:var(--ss-primary-dark);">{t['name']}</div>
                        <div style="font-size:0.8rem;color:var(--ss-text-muted);">{t['category']} &middot; {region}</div>
                        </div></div>""",
                    unsafe_allow_html=True,
                )
                st.write(t["note"])
                speak_button(
                    f"{t['name']}, a {t['category'].lower()} of the North Eastern Region. {t['note']}",
                    key=f"voice_trad_{key_suffix}_{t['id']}",
                )

    if editable:
        with st.expander("+ Add a tradition (name & photo)"):
            with st.form(f"add_tradition_form_{key_suffix}", clear_on_submit=True):
                name = st.text_input("Name (e.g. Bihu Dance, Gamosa)", key=f"trad_name_{key_suffix}")
                category = st.selectbox("Category", TRADITION_CATEGORIES, key=f"trad_cat_{key_suffix}")
                state_codes = [""] + list(db.STATES.keys())
                tradition_state = st.selectbox(
                    "State this belongs to",
                    state_codes,
                    format_func=lambda c: "All states (generic)" if c == "" else db.STATES[c],
                    key=f"trad_state_{key_suffix}",
                    help="A patient's own state shows in their 'Know Your Roots' game first, "
                         "regardless of their UI language. Pick 'All states' if it isn't tied "
                         "to one specific NER state.",
                )
                note = st.text_area("A short note about it", "", key=f"trad_note_{key_suffix}")
                photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png"], key=f"trad_photo_{key_suffix}")
                if st.form_submit_button("Save"):
                    if name:
                        try:
                            photo_path = db.save_uploaded_photo(photo.getvalue(), photo.name) if photo else None
                        except ValueError as e:
                            st.error(str(e))
                        else:
                            db.add_tradition(name, category, note, photo_path, tradition_state)
                            st.success("Saved 💛")
                            st.rerun()
                    else:
                        st.warning("Please enter a name.")


def render_memory_box(patient):
    if st.button("← Back"):
        goto("home")
    st.header(L("box"))
    render_family_gallery(patient, key_suffix="box")


def render_reminders(patient):
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


def render_patient(patient):
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1.1rem;">
            <div class="ss-badge ss-badge-sm"
                 style="background:linear-gradient(135deg,var(--ss-primary-light),var(--ss-primary));border:2px solid var(--ss-primary-dark);box-shadow:0 4px 10px rgba(31,51,47,0.2);">🧠</div>
            <div>
                <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.35rem;
                            color:var(--ss-primary-dark);line-height:1.15;">{L('app')}</div>
                <div style="font-size:0.82rem;color:var(--ss-text-muted);">{L('sub')}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    page_renderers = {
        "home": render_patient_home,
        "games_menu": render_games_menu,
        "game_memory": render_game_memory,
        "game_pattern": render_game_pattern,
        "game_traditions": render_game_traditions,
        "memory_box": render_memory_box,
        "reminders": render_reminders,
    }
    page_renderers.get(ss.page, render_patient_home)(patient)


# --------------------------------------------------------------------- run --

def run():
    """Entry point called by app.py on every Streamlit rerun."""
    st.set_page_config(page_title="Neuronova", page_icon="🧠", layout="centered")

    ss.setdefault("page", "welcome")
    ss.setdefault("lang", "en")
    ss.setdefault("role", "Patient")

    patients = db.get_patients()
    valid_ids = {p["id"] for p in patients}
    if ss.get("patient_id") not in valid_ids:
        # Stale id from a previous session (e.g. demo data was reseeded and
        # SQLite's AUTOINCREMENT assigned new ids) -- fall back instead of
        # crashing with StopIteration in current_patient().
        ss.patient_id = patients[0]["id"]

    inject_global_css()

    if ss.page == "welcome":
        render_welcome()
        st.stop()

    if ss.page == "landing":
        render_landing()
        st.stop()

    if ss.page == "login":
        render_login(patients)
        st.stop()

    render_sidebar(patients)
    patient = current_patient(patients)

    if ss.role == "Caregiver":
        render_caregiver(patient)
    else:
        render_patient(patient)
