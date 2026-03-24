"""Human-readable durations (seconds → min / sec, or hr for long spans)."""


def format_duration_seconds(seconds) -> str:
    """
    Quiz-friendly: prefer minutes + seconds (3600 → "60 min", 90 → "1 min 30 sec").
    Uses hours only when total time is 2+ hours (120+ minutes).
    """
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "—"
    s = max(0, s)
    if s < 60:
        return f"{s} sec" if s != 1 else "1 sec"

    m_total, sec = divmod(s, 60)

    if m_total < 120:
        if sec:
            return f"{m_total} min {sec} sec"
        return f"{m_total} min" if m_total != 1 else "1 min"

    h, m = divmod(m_total, 60)
    parts = []
    if h:
        parts.append("1 hr" if h == 1 else f"{h} hrs")
    if m:
        parts.append(f"{m} min")
    if sec:
        parts.append(f"{sec} sec")
    return " ".join(parts) if parts else "0 sec"
