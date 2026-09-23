"""Нормализация сроков: «к пятнице», «до конца недели», «через 2 недели» → дата (ISO)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from dateutil import parser as _du_parser

_WEEKDAYS_RU = {
    "понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3,
    "пятница": 4, "суббота": 5, "воскресенье": 6,
}
_WEEKDAYS_KK = {
    "дуйсенбі": 0, "сейсенбі": 1, "сәрсенбі": 2, "бейсенбі": 3,
    "жұма": 4, "сенбі": 5, "жексенбі": 6,
}
_WEEKDAYS = {**_WEEKDAYS_RU, **_WEEKDAYS_KK}
_ALIASES = {"завтра": 1, "завтрашний": 1, "послезавтра": 2, "сегодня": 0}

_REL = [
    (re.compile(r"(?:через|спустя)\s+(\d+)\s*(дн|день|дня|недел|нед|месяц|мес|год|лет|года)", re.I), "rel"),
    (re.compile(r"(?:в течение|в течении)\s+(\d+)\s*(дн|день|дня|недел|нед|месяц|мес|год|лет)", re.I), "rel"),
    (re.compile(r"(?:к|до|не позднее)\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", re.I), "date"),
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), "date"),
    (re.compile(r"(?:до|к)\s+(конца|конец)\s+(недели|месяца|года)", re.I), "period"),
    (re.compile(r"\bследующ\w+\s+(недел\w+|месяц\w*)", re.I), "relweek"),
]

_MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_MONTHS_KK = {
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
}
_MONTHS = {**_MONTHS_RU, **_MONTHS_KK}
_MM_RE = "|".join(_MONTHS)
_MONTH_NAME_RE = re.compile(
    rf"(?:до |к |по |не позднее )*(\d{{1,2}})\s+({_MM_RE})", re.I)

_DAYS_FOR_UNIT = {"дн": "days", "день": "days", "дня": "days", "недел": "weeks",
                  "нед": "weeks", "месяц": "months", "мес": "months",
                  "год": "years", "года": "years", "лет": "years"}


_WEEKDAY_STEMS = (
    ("понедельн", 0), ("понеділ", 0), ("вторн", 1), ("сейсенбі", 1), ("дуйсенбі", 0),
    ("сред", 2), ("сәрсенбі", 2), ("четверг", 3), ("бейсенбі", 3),
    ("пятниц", 4), ("жұма", 4), ("суббот", 5), ("сенбі", 5),
    ("воскрес", 6), ("жексенбі", 6),
)


def _match_weekday(t: str) -> int | None:
    for stem, idx in _WEEKDAY_STEMS:
        if re.search(rf"\b{stem}\w*", t):
            return idx
    return None


def _next_weekday(ref: date, target: int) -> date:
    days_ahead = (target - ref.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return ref + timedelta(days=days_ahead)


def _add_units(ref: date, num: int, unit: str) -> date:
    u = _DAYS_FOR_UNIT.get(unit, "days")
    if u == "days":
        return ref + timedelta(days=num)
    if u == "weeks":
        return ref + timedelta(weeks=num)
    if u == "months":
        y, m = ref.year + (ref.month - 1 + num) // 12, (ref.month - 1 + num) % 12 + 1
        return date(y, m, min(ref.day, 28))
    if u == "years":
        try:
            return ref.replace(year=ref.year + num)
        except ValueError:
            return ref.replace(year=ref.year + num, day=28)
    return ref


def normalize_deadline(text: str, ref: date | None = None) -> str | None:
    """Пытается извлечь из фразы конкретную дату. Возвращает 'YYYY-MM-DD' или None."""
    if not text:
        return None
    ref = ref or date.today()
    t = text.strip().lower()
    if not t or len(t) < 4:
        return None

    # явные даты
    for pat, kind in _REL:
        m = pat.search(t)
        if not m:
            continue
        if kind == "date":
            if len(m.groups()) == 3 and m.group(3):
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                y = y + 2000 if y < 100 else y
            else:
                d, mo = int(m.group(1)), int(m.group(2))
                y = ref.year
                if date(y, mo, d) < ref:
                    y += 1
            try:
                dt = date(y, mo, d)
            except ValueError:
                return None
            return dt.isoformat()
        if kind == "period":
            unit = m.group(2)
            if unit == "недели":
                return _next_weekday(ref, 6).isoformat()  # воскресенье
            if unit == "месяца":  # последний день текущего месяца
                y, mo = (ref.year + 1, 1) if ref.month == 12 else (ref.year, ref.month + 1)
                return (date(y, mo, 1) - timedelta(days=1)).isoformat()
            if unit == "года":
                return date(ref.year, 12, 31).isoformat()
        if kind == "rel":
            num = int(m.group(1))
            return _add_units(ref, num, m.group(2)).isoformat()
        if kind == "relweek":
            unit = m.group(1)
            if unit.startswith("недел"):
                return _next_weekday(ref, 6).isoformat()
            if unit.startswith("месяц"):  # последний день следующего месяца
                y, mo = (ref.year + 1, 1) if ref.month == 12 else (ref.year, ref.month + 1)
                return (date(y, mo, 1) - timedelta(days=1)).isoformat()

    # «к пятнице», «в среду», «до жұма», «в следующий понедельник»
    wd = _match_weekday(t)
    if wd is not None:
        if "следующ" in t:
            return (_next_weekday(ref, wd) + timedelta(days=7)).isoformat()
        return _next_weekday(ref, wd).isoformat()

    # «30 сентября», «30 қыркүйек»
    m = _MONTH_NAME_RE.search(t)
    if m:
        d, mo = int(m.group(1)), _MONTHS[m.group(2).lower()]
        y = ref.year
        try:
            if date(y, mo, d) < ref:
                y += 1
            dt = date(y, mo, d)
        except ValueError:
            return None
        return dt.isoformat()

    # «до конца недели/месяца» без «конца»
    if re.search(r"(?:до|к)\s+конц", t):
        if "недел" in t:
            return _next_weekday(ref, 6).isoformat()
        if "месяц" in t:
            nm = date(ref.year, ref.month, 1) + timedelta(days=32)
            return (date(nm.year, nm.month, 1) - timedelta(days=1)).isoformat()

    # слова-алиасы
    for alias, off in _ALIASES.items():
        if re.search(rf"\b{alias}\b", t):
            return (ref + timedelta(days=off)).isoformat()

    # попытка распарсить «20 сентября», «сентября 20»
    try:
        _du_parser.parse(t, default=ref, fuzzy=True, dayfirst=True)
    except (ValueError, OverflowError):
        return None
    return None


def deadline_raw_to_display(raw: str | None, iso: str | None) -> str:
    """Человекочитаемый срок для итогового протокола."""
    if iso:
        try:
            return f"{iso} (из: {raw or '—'})"
        except Exception:
            return iso
    return raw or "не указан"


if __name__ == "__main__":
    ref = date(2026, 9, 23)  # среда
    tests = ["к пятнице", "до конца недели", "через 2 недели", "завтра",
             "до 28.09", "к жұма", "в течение 5 дней", "по 30 сентября", "следующий месяц"]
    for s in tests:
        print(f"{s!r:35} → {normalize_deadline(s, ref)}")