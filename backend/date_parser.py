"""Conservative RU/KK dates, always anchored to the meeting date."""

import re
from datetime import date, timedelta

WEEKDAYS = [
    (r"понедельн\w*|дүйсенбі\w*", 0),
    (r"вторн\w*|сейсенбі\w*", 1),
    (r"сред[ауы]|сәрсенбі\w*", 2),
    (r"четверг\w*|бейсенбі\w*", 3),
    (r"пятниц\w*|жұма\w*", 4),
    (r"суббот\w*|сенбі\w*", 5),
    (r"воскресень\w*|жексенбі\w*", 6),
]
NUMBERS = {
    "один": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "бір": 1,
    "екі": 2,
    "үш": 3,
    "төрт": 4,
    "бес": 5,
}


def normalize_deadline(text: str | None, ref: date) -> str | None:
    if not text:
        return None
    t = text.lower()
    if re.search(
        r"кон(ца|ец)\s+(недел|месяц)|следующ\w*\s+(недел|месяц)|апта\w*|айдың\s+соң|келесі\s+ай",
        t,
    ):
        return None
    try:
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
        if m:
            return date.fromisoformat(m[1]).isoformat()
        m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?\b", t)
        if m:
            return date(int(m[3] or ref.year), int(m[2]), int(m[1])).isoformat()
    except ValueError:
        return None
    for word, days in [
        ("послезавтра", 2),
        ("бүрсігүні", 2),
        ("завтра", 1),
        ("ертең", 1),
        ("сегодня", 0),
        ("бүгін", 0),
    ]:
        if re.search(r"\b" + word + r"\b", t):
            return (ref + timedelta(days=days)).isoformat()
    n = r"(\d+|" + "|".join(NUMBERS) + ")"
    m = re.search(r"(?:через|спустя)\s+" + n + r"\s+д(?:ня|ней|ень)", t)
    if not m:
        m = re.search(n + r"\s+күн(?:нен)?\s+кейін", t)
    if m:
        count = int(m[1]) if m[1].isdigit() else NUMBERS[m[1]]
        return (ref + timedelta(days=count)).isoformat()
    matches = [
        (m.start(), day)
        for pat, day in WEEKDAYS
        for m in re.finditer(r"\b(?:" + pat + r")\b", t)
    ]
    if matches:
        day = sorted(matches)[-1][1]
        delta = (day - ref.weekday()) % 7
        return (ref + timedelta(days=delta)).isoformat() if delta else None
    return None
