"""
cognitive_ai.py — the "AI" behind Smriti Sathi's caregiver alerts.

This is intentionally a transparent, explainable model rather than a black
box: it fits a linear trend to a patient's daily average game score over
time (numpy least-squares regression), compares recent vs. earlier
performance, and turns that into a risk classification and a
plain-language recommendation a caregiver or ASHA worker can act on.

Swap `analyze_trend` for a heavier model (e.g. an LSTM over multi-modal
signals) later without changing anything that calls it — the input/output
contract stays the same.
"""

from datetime import datetime
import numpy as np


def _daily_averages(score_rows):
    """Collapse raw (possibly multiple-per-day) score rows into one
    average-per-day series, sorted by date."""
    by_day = {}
    for row in score_rows:
        day = row["played_at"][:10]  # YYYY-MM-DD
        by_day.setdefault(day, []).append(row["score"])
    days_sorted = sorted(by_day.keys())
    daily_avg = [float(np.mean(by_day[d])) for d in days_sorted]
    return days_sorted, daily_avg


def analyze_trend(score_rows):
    """
    Parameters
    ----------
    score_rows : sequence of sqlite3.Row (must have 'played_at' and 'score')

    Returns
    -------
    dict with keys:
        has_data        bool
        days            list[str]
        daily_avg       list[float]
        slope_per_day   float   (points/day, +ve = improving)
        recent_avg      float   (last 7 days)
        previous_avg    float   (7 days before that)
        trend           str     "Improving" | "Stable" | "Declining"
        risk            str     "Low" | "Medium" | "High"
        recommendation  str     plain-language caregiver guidance
    """
    days, daily_avg = _daily_averages(score_rows)

    if len(daily_avg) < 3:
        return {
            "has_data": False,
            "days": days,
            "daily_avg": daily_avg,
            "slope_per_day": 0.0,
            "recent_avg": float(np.mean(daily_avg)) if daily_avg else 0.0,
            "previous_avg": 0.0,
            "trend": "Not enough data",
            "risk": "Unknown",
            "recommendation": "Encourage a few more days of play to build a reliable trend.",
        }

    x = np.arange(len(daily_avg))
    slope, intercept = np.polyfit(x, daily_avg, 1)

    recent = daily_avg[-7:]
    previous = daily_avg[-14:-7] if len(daily_avg) >= 14 else daily_avg[:-7]
    recent_avg = float(np.mean(recent)) if recent else float(np.mean(daily_avg))
    previous_avg = float(np.mean(previous)) if previous else recent_avg

    if slope <= -1.5 or (previous_avg - recent_avg) >= 12:
        trend, risk = "Declining", "High"
        recommendation = (
            "Scores have dropped noticeably over the last two weeks. "
            "Consider a caregiver check-in and a consultation with a doctor "
            "or the nearest primary health centre."
        )
    elif slope <= -0.3 or (previous_avg - recent_avg) >= 5:
        trend, risk = "Declining", "Medium"
        recommendation = (
            "A gentle downward trend is visible. Try shorter, more frequent "
            "game sessions and confirm medicines are being taken on time."
        )
    elif slope >= 0.5:
        trend, risk = "Improving", "Low"
        recommendation = "Great progress — the current routine is working well, keep it going."
    else:
        trend, risk = "Stable", "Low"
        recommendation = "Engagement is steady. No action needed beyond the usual routine."

    return {
        "has_data": True,
        "days": days,
        "daily_avg": [round(v, 1) for v in daily_avg],
        "slope_per_day": round(float(slope), 3),
        "recent_avg": round(recent_avg, 1),
        "previous_avg": round(previous_avg, 1),
        "trend": trend,
        "risk": risk,
        "recommendation": recommendation,
    }


def medicine_adherence(reminder_rows):
    """Simple adherence % for today's medicine-type reminders."""
    meds = [r for r in reminder_rows if r["type"] == "Medicine"]
    if not meds:
        return 100.0, 0, 0
    done = sum(1 for r in meds if r["done"])
    pct = round(100.0 * done / len(meds), 1)
    return pct, done, len(meds)
