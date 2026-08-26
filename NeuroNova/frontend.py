"""
frontend.py — all Streamlit UI/rendering code for Neuronova.

Every screen, layout, style and navigation flow the user sees lives here.
db.py, cognitive_ai.py and voice.py stay backend-only (data, analytics, speech);
app.py is just the entry point that wires the database up and calls run().
"""

import os
import random
import streamlit as st
import pandas as pd

import db
import cognitive_ai
import voice

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

ss = st.session_state


# ------------------------------------------------------------------ helpers --

def goto(page):
    ss.page = page
    st.rerun()


def L(key):
    return LABELS[ss.lang][key]


def current_patient(patients):
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
                    <div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-light);">{title}</div>
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
                    backdrop-filter:blur(14px);box-shadow:0 0 20px {color}33;margin-bottom:1rem;">
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
        "Stable": ("var(--ss-primary)", "rgba(0,229,255,0.12)", "➖"),
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
    st.write("")
    st.write("")
    st.write("")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(
            """
            <div style="background:var(--ss-card);border-radius:24px;padding:2.6rem 2rem;
                        text-align:center;backdrop-filter:blur(14px);box-shadow:0 0 40px rgba(0,229,255,0.14);
                        border:1px solid rgba(0,229,255,0.22);">
                <div style="font-size:3rem;filter:drop-shadow(0 0 16px rgba(0,229,255,0.6));">🧠</div>
                <h2 style="margin:0.6rem 0 0.3rem;color:var(--ss-primary-light);">Hi there 👋</h2>
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
            ss.page = "home"
            st.rerun()
    st.caption("SIH26003 — working prototype")


def render_sidebar(patients, patient_names):
    with st.sidebar:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.6rem;">
                <div class="ss-badge ss-badge-sm"
                     style="background:linear-gradient(135deg,#101a33,#1c1240);border:2px solid var(--ss-primary);box-shadow:0 0 14px rgba(0,229,255,0.4);">🧠</div>
                <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.3rem;color:var(--ss-primary-light);">
                    Neuronova</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        ss.role = st.radio("View", ["Patient", "Caregiver"], index=["Patient", "Caregiver"].index(ss.role))

        sel_name = st.selectbox("Demo profile", patient_names, index=patient_names.index(current_patient(patients)["name"]))
        new_patient = next(p for p in patients if p["name"] == sel_name)
        if new_patient["id"] != ss.patient_id and new_patient["language"] in LABELS:
            ss.lang = new_patient["language"]
        ss.patient_id = new_patient["id"]

        initials = "".join(w[0] for w in new_patient["name"].split()[:2]).upper()
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.7rem;background:var(--ss-card);
                        border:1px solid rgba(0,229,255,0.12);border-radius:14px;padding:0.7rem 0.9rem;
                        margin:0.5rem 0 0.9rem;box-shadow:0 4px 12px rgba(0,229,255,0.06);">
                {avatar_html(initials)}
                <div>
                    <div style="font-weight:700;color:var(--ss-primary-light);">{new_patient['name']}</div>
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


def render_caregiver(patient):
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.3rem;">
            {icon_badge_html('📊', 'linear-gradient(135deg,var(--ss-secondary),var(--ss-secondary-dark))')}
            <div>
                <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.7rem;
                            color:var(--ss-primary-light);line-height:1.1;">Caregiver Dashboard</div>
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
            st.line_chart(df, color="#00e5ff")

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
                        color:var(--ss-primary-light);">{L('greeting')}, {patient['name']}</div>
        </div>
        <div style="background:var(--ss-card);border:1px solid rgba(0,229,255,0.1);border-radius:16px;
                    padding:1rem 1.2rem;box-shadow:0 6px 16px rgba(0,229,255,0.08);margin-bottom:1.3rem;">
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
                        <div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-light);">{L('call')}</div>
                        <div style="font-size:0.85rem;color:var(--ss-text-muted);">Priya Bora, Daughter</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Call now", key="tile_call", use_container_width=True):
                st.toast("📞 Calling Priya Bora (Daughter)...")


def render_games_menu(patient):
    if st.button("← Back"):
        goto("home")
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:1rem;">
            {icon_badge_html('🧠', 'linear-gradient(135deg,var(--ss-primary),var(--ss-primary-light))')}
            <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.5rem;
                        color:var(--ss-primary-light);">Memory Games</div></div>""",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.7rem;">
                {icon_badge_html('🃏', 'linear-gradient(135deg,var(--ss-primary),var(--ss-primary-light))')}
                <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-light);">Memory Match</div>
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
                <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-light);">Pattern Recall</div>
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
                <div><div style="font-weight:700;font-size:1.08rem;color:var(--ss-primary-light);">Who Is This?</div>
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


def render_game_pattern(patient):
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


def render_game_family(patient):
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
                            justify-content:center;font-family:'Exo 2',sans-serif;font-weight:700;
                            font-size:2rem;color:var(--ss-primary-light);
                            background:linear-gradient(135deg,#101a33 0%,#1c1240 100%);
                            border:3px solid var(--ss-primary);box-shadow:0 8px 20px rgba(0,229,255,0.18);">
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


def render_memory_box(patient):
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
                        <div><div style="font-weight:700;color:var(--ss-primary-light);">{p['name']}</div>
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
                 style="background:linear-gradient(135deg,#101a33,#1c1240);border:2px solid var(--ss-primary);box-shadow:0 0 14px rgba(0,229,255,0.4);">🧠</div>
            <div>
                <div style="font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.35rem;
                            color:var(--ss-primary-light);line-height:1.15;">{L('app')}</div>
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
        "game_family": render_game_family,
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
    patient_names = [p["name"] for p in patients]
    ss.setdefault("patient_id", patients[0]["id"])

    inject_global_css()

    if ss.page == "welcome":
        render_welcome()
        st.stop()

    if ss.page == "landing":
        render_landing()
        st.stop()

    render_sidebar(patients, patient_names)
    patient = current_patient(patients)

    if ss.role == "Caregiver":
        render_caregiver(patient)
    else:
        render_patient(patient)
