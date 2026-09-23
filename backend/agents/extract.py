"""Извлечение поручений из транскрипта.

Режимы:
  * LLM (OpenAI/NVIDIA) — структурный JSON по схеме; качественный анализ
    смешанной русско-казахской речи, сроков и ответственных.
  * Fallback (без сети) — детерминированные правила: маркеры глаголов,
    имена собственные, регулярные выражения сроков.

После извлечения каждый срок нормализуется (date_parser), а ответственный
привязывается к конкретному говорящему из диаризации (по имени в репликах).
"""
from __future__ import annotations

import json
import re
from datetime import date

from date_parser import normalize_deadline

# маркеры поручений (рус + каз): «подготовить», «Қамтамасыз ету» и т.п.
_TASK_VERBS = [
    r"подготовить", r"подготовь", r"подготовит", r"подготовл",
    r"разработать", r"разрработ", r"обеспечить", r"предоставить", r"предостав",
    r"направить", r"направ", r"провести", r"провед", r"организовать", r"организу",
    r"согласовать", r"согласу", r"прошу подготовить", r"нужно?(| сопровождать)",
    r"изуч\w+ и", r"довести", r"актуализировать", r"актуализироват",
    r"внести", r"подготову", r"сверстать", r"сверста",
    r"составить", r"проработать", r"уточнить", r"уточн",
    r"направить", r"передать", r"передач",
    r"қамтамасыз ет\w*", r"дайында\w*", r"жібер\w*", r"анықта\w*",
    r"ұйымдастыр\w*", r"ұсын\w*", r"әзірле\w*",
    r"тапсырма\w*", r"орындау\w*", r"жоспар\w*"
]
_TASK_RE = re.compile(r"\b(" + "|".join(_TASK_VERBS) + r")\b", re.I)

# имена собственные (кириллица + каз. буквы), Капит_{a-z+й..}
_NAME_RE = re.compile(
    r"(?<![а-яёқғңүұәіөһa-z])[А-ЯЁҚҒҢҮҰӘІӨҺ][а-яёқғңүұәіөһ]{2,}\b")

_PRIORITY_RE = re.compile(r"\b(срочно|важно|безотлагательно|первоочередн|в первую очередь|мақсат|шұғыл)\b", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+\s*|\n+", text) if len(s.strip()) > 3]


def _first_capitals(text: str) -> list[str]:
    return [m.group(0) for m in _NAME_RE.finditer(text)]


# ---------------------------------------------------------------- привязка
def bind_owner_to_speaker(owner: str, blocks: list[dict]) -> dict | None:
    """Ищет имя ответственного в репликах говорящих → speaker_id/label."""
    if not owner:
        return None
    tokens = [w for w in re.split(r"\W+", owner) if len(w) >= 3]
    if not tokens:
        return None
    scores: dict[str, int] = {}
    for b in blocks:
        low = b["text"].lower()
        hits = sum(1 for t in tokens if t.lower() in low)
        if hits:
            scores[b["speaker"]] = max(scores.get(b["speaker"], 0), hits)
    if not scores:
        return None
    best = max(scores, key=scores.get)
    idx = next((bl["speaker_idx"] for bl in blocks if bl["speaker"] == best), None)
    return {"speaker_id": idx, "speaker_label": best}


def _perform_bind(owner: str, blocks: list[dict]) -> dict:
    b = bind_owner_to_speaker(owner, blocks)
    return {
        "speaker_label": b["speaker_label"] if b else None,
        "speaker_id": b["speaker_id"] if b else None,
    }


# ---------------------------------------------------------------- LLM-путь
_LLM_SYSTEM = """Ты — модуль автоматического протоколирования совещаний.
По размеченному транскрипту найди ПОРУЧЕНИЯ: задачи, которые поручены конкретному
человеку или отделу, с указанием срока. Работает русский, казахский и смешанная
(«шала-казах») речь.

Верни ТОЛЬКО JSON без пояснений в формате:
{"assignments": [
  {"task": "суть поручения одним предложением (язык оригинала)",
   "owner": "кому поручено (ФИО/должность/отдел) или null",
   "deadline_raw": "формулировка срока как в записи или null",
   "priority": "high|medium|low",
   "speaker_label": "метка говорящего из транскрипта (Говорящий N), если понятно, кто отвечает, иначе null"}
]}
Не выдумывай поручения, которых нет в транскрипте."""


def _validate(p: dict) -> bool:
    return isinstance(p.get("assignments"), list) and all(
        isinstance(a, dict) and isinstance(a.get("task"), str) and a["task"]
        for a in p["assignments"])


def extract_assignments_llm(blocks: list[dict], llm) -> list[dict]:
    lines = []
    for b in blocks:
        lines.append(f"[{b['speaker']}] {b['text']}")
    transcript = "\n".join(lines)
    parsed = llm.chat_json(
        _LLM_SYSTEM,
        f"Транскрипт совещания:\n{transcript}",
        validator=_validate,
    )
    out = []
    for a in parsed["assignments"]:
        task = str(a.get("task", "")).strip()
        if len(task) < 5:
            continue
        owner_raw = str(a.get("owner") or "").strip()
        dl_raw = str(a.get("deadline_raw") or "").strip()
        iso = normalize_deadline(dl_raw) if dl_raw else None
        priority = str(a.get("priority", "medium")).lower()
        if priority not in ("high", "medium", "low"):
            priority = "medium"
        bind = _perform_bind(owner_raw, blocks) if owner_raw else {}
        out.append({
            "task": task,
            "owner": owner_raw or None,
            "deadline_raw": dl_raw or None,
            "deadline": iso,
            "priority": priority,
            "speaker_label": bind.get("speaker_label") or (str(a.get("speaker_label") or "") or None),
            "speaker_id": bind.get("speaker_id"),
            "source": "llm",
        })
    return out


# ------------------------------------------------------ Fallback (правила)
def extract_assignments_rules(blocks: list[dict]) -> list[dict]:
    out: list[dict] = []
    for b in blocks:
        cands = [s for s in _sentences(b["text"]) if _TASK_RE.search(s)]
        for s in cands:
            owner = None
            capitals = _first_capitals(s)
            if capitals:
                # приоритет именам рядом с «поручаю/ответственн/прошу»
                owner = _name_near_marker(s) or capitals[0]
            dl_raw = _deadline_in_block(b["text"], s)
            task = re.sub(r"\s+", " ", s).strip()
            priority = "high" if _PRIORITY_RE.search(task) else "medium"
            bind = _perform_bind(owner, [b]) if owner else {}
            out.append({
                "task": task,
                "owner": owner,
                "deadline_raw": dl_raw,
                "deadline": normalize_deadline(dl_raw) if dl_raw else None,
                "priority": priority,
                "speaker_label": bind.get("speaker_label") or b["speaker"],
                "speaker_id": bind.get("speaker_id") if bind else b["speaker_idx"],
                "source": "rules",
            })
    return out


_MARKER_RE = re.compile(
    r"(?i:поручаю|поручается|поручаем|ответственн|прошу|беру на себя|принимает|"
    r"жауапты|тапсырамын)\s*(?::|\s+)?\s*"
    r"([А-ЯЁҚҒҢҮҰӘІӨҺ][а-яёқғңүұәіөһ]*(?:\s+[А-ЯЁҚҒҢҮҰӘІӨҺ][а-яёқғңүұәіөһ]*)?)")


def _name_near_marker(text: str) -> str | None:
    m = _MARKER_RE.search(text)
    return m.group(1).strip() if m else None


def _deadline_in_block(block_text: str, sentence: str) -> str | None:
    cands = [sentence] + [s for s in _sentences(block_text) if s != sentence][:2]
    for s in cands:
        if re.search(r"\b(?:к|до|в течение|через|завтра|послезавтра|срок|конц|пятниц|жұма|сіз)"
                     r"|\b\d{1,2}[./]\d", s, re.I):
            return s
    return None


def extract_assignments(blocks: list[dict], llm) -> dict:
    """Возвращает {'assignments': [...], 'mode': 'llm'|'rules'}."""
    if llm.available:
        try:
            return {"assignments": extract_assignments_llm(blocks, llm), "mode": "llm"}
        except Exception as e:  # LLM недоступен/ошибка → правила
            print(f"[extract] LLM недоступен, fallback rules: {e}")
    return {"assignments": extract_assignments_rules(blocks), "mode": "rules"}