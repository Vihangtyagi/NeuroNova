"""
cognitive_ai.py — the "AI" behind Neuronova's caregiver alerts.

Feature engineering (least-squares trend slope, recent-vs-earlier average,
day-to-day volatility) feeds a scikit-learn RandomForestClassifier that
classifies a patient's trend into a risk category and plain-language
recommendation. The classifier is trained at import time on simulated
patient trajectories and validated on a held-out split (see
MODEL_ACCURACY / MODEL_INFO below) -- swap in real logged multi-patient
history for the synthetic training set once enough has been collected,
without changing analyze_trend()'s input/output contract.
"""

from datetime import datetime
import random
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Each class pairs a human trend label with a risk level and caregiver
# recommendation. "decline_high"/"decline_medium" split what used to be a
# single hand-picked slope threshold into two classifier-learned bands.
_CLASS_INFO = {
    "decline_high": (
        "Declining",
        "High",
        "Scores have dropped noticeably over the last two weeks. "
        "Consider a caregiver check-in and a consultation with a doctor "
        "or the nearest primary health centre.",
    ),
    "decline_medium": (
        "Declining",
        "Medium",
        "A gentle downward trend is visible. Try shorter, more frequent "
        "game sessions and confirm medicines are being taken on time.",
    ),
    "stable_low": (
        "Stable",
        "Low",
        "Engagement is steady. No action needed beyond the usual routine.",
    ),
    "improve_low": (
        "Improving",
        "Low",
        "Great progress — the current routine is working well, keep it going.",
    ),
}

# Ground-truth daily-improvement rate (points/day) each class is simulated
# from when building the training set -- deliberately mirrors the manual
# thresholds the model replaces, so the swap doesn't change demo behaviour.
_SLOPE_RANGES = {
    "decline_high": (-3.0, -1.5),
    "decline_medium": (-1.4, -0.35),
    "stable_low": (-0.3, 0.45),
    "improve_low": (0.5, 2.2),
}

_SAMPLES_PER_CLASS = 150


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


def _extract_features(daily_avg):
    """Turn a daily-average score series into the feature vector the
    classifier trains and predicts on: trend slope, recent vs. earlier
    average, the size of that gap, and day-to-day volatility."""
    x = np.arange(len(daily_avg))
    slope, _ = np.polyfit(x, daily_avg, 1)

    recent = daily_avg[-7:]
    previous = daily_avg[-14:-7] if len(daily_avg) >= 14 else daily_avg[:-7]
    recent_avg = float(np.mean(recent)) if recent else float(np.mean(daily_avg))
    previous_avg = float(np.mean(previous)) if previous else recent_avg
    volatility = float(np.std(daily_avg))

    features = [float(slope), recent_avg, previous_avg, recent_avg - previous_avg, volatility]
    return features, float(slope), recent_avg, previous_avg


def _simulate_trajectory(rng, true_slope, n_days):
    """Generate one synthetic patient's noisy daily-average score series
    from a known underlying improvement/decline rate, so the classifier
    has to learn to recover the true trend category from noisy features
    -- the same task it faces on real (also noisy) patient data."""
    baseline = rng.uniform(45, 90)
    noise_sd = rng.uniform(3, 9)
    return [
        min(100.0, max(0.0, baseline + true_slope * day + rng.gauss(0, noise_sd)))
        for day in range(n_days)
    ]


def _build_training_set(seed=42):
    rng = random.Random(seed)
    X, y = [], []
    for label, (lo, hi) in _SLOPE_RANGES.items():
        for _ in range(_SAMPLES_PER_CLASS):
            true_slope = rng.uniform(lo, hi)
            # Vary history length (4-21 days) so the model also learns the
            # short-history feature behaviour real early-stage patients hit.
            n_days = rng.randint(4, 21)
            daily = _simulate_trajectory(rng, true_slope, n_days)
            feats, *_ = _extract_features(daily)
            X.append(feats)
            y.append(label)
    return np.array(X), np.array(y)


def _train_model():
    X, y = _build_training_set()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=7, stratify=y
    )
    model = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=7)
    model.fit(X_train, y_train)
    accuracy = accuracy_score(y_test, model.predict(X_test))
    # Ship the model refit on the full synthetic set; the accuracy above
    # (from the held-out split) is what's reported as MODEL_ACCURACY.
    model.fit(X, y)
    return model, round(float(accuracy), 3)


_MODEL, MODEL_ACCURACY = _train_model()
_TOTAL_TRAINING_SAMPLES = _SAMPLES_PER_CLASS * len(_SLOPE_RANGES)
MODEL_INFO = (
    f"Random Forest classifier · trained on {_TOTAL_TRAINING_SAMPLES} simulated "
    f"patient trajectories · {MODEL_ACCURACY * 100:.0f}% accuracy on a held-out test split"
)


def analyze_trend(score_rows):
    """
    Parameters
    ----------
    score_rows : sequence of sqlite3.Row (must have 'played_at' and 'score')

    Returns
    -------
    dict with keys:
        has_data          bool
        days              list[str]
        daily_avg         list[float]
        slope_per_day     float   (points/day, +ve = improving)
        recent_avg        float   (last 7 days)
        previous_avg      float   (7 days before that)
        trend             str     "Improving" | "Stable" | "Declining"
        risk              str     "Low" | "Medium" | "High"
        recommendation    str     plain-language caregiver guidance
        model_confidence  float   0-1, the classifier's confidence in this call
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
            "model_confidence": 0.0,
        }

    features, slope, recent_avg, previous_avg = _extract_features(daily_avg)
    probabilities = _MODEL.predict_proba([features])[0]
    label = _MODEL.classes_[int(np.argmax(probabilities))]
    confidence = float(np.max(probabilities))
    trend, risk, recommendation = _CLASS_INFO[label]

    return {
        "has_data": True,
        "days": days,
        "daily_avg": [round(v, 1) for v in daily_avg],
        "slope_per_day": round(slope, 3),
        "recent_avg": round(recent_avg, 1),
        "previous_avg": round(previous_avg, 1),
        "trend": trend,
        "risk": risk,
        "recommendation": recommendation,
        "model_confidence": round(confidence, 3),
    }


def medicine_adherence(reminder_rows):
    """Simple adherence % for today's medicine-type reminders."""
    meds = [r for r in reminder_rows if r["type"] == "Medicine"]
    if not meds:
        return 100.0, 0, 0
    done = sum(1 for r in meds if r["done"])
    pct = round(100.0 * done / len(meds), 1)
    return pct, done, len(meds)
