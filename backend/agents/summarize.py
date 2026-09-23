"""Агент саммари: краткая выжимка совещания (LLM или шаблон)."""
from __future__ import annotations

_SYS = """Ты — секретарь совещания. Составь КРАТКОЕ саммари по транскрипту (3-6 пунктов):
тема, ключевые решения, что поручено, кому, к какому сроку. Язык — русский.
Верни ТОЛЬКО JSON: {"summary": ["пункт 1", "пункт 2", ...]}."""


def summarize_llm(blocks: list[dict], llm) -> list[str]:
    lines = "\n".join(f"[{b['speaker']}] {b['text']}" for b in blocks)
    parsed = llm.chat_json(_SYS, f"Транскрипт:\n{lines}",
                           validator=lambda p: isinstance(p.get("summary"), list))
    return [str(x).strip() for x in parsed["summary"] if str(x).strip()]


def summarize_rules(blocks: list[dict], assignments: list[dict]) -> list[str]:
    duration = round(sum(b["end"] - b["start"] for b in blocks) / 60, 1)
    out = [
        f"Совещание: {len(blocks)} реплик, участвовало говорящих: "
        f"{len({b['speaker'] for b in blocks})}, продолжительность дискуссии ≈ {duration} мин.",
    ]
    if assignments:
        owners = [a["owner"] for a in assignments if a.get("owner")]
        out.append(
            f"Выделено поручений: {len(assignments)}"
            + (f", ответственные: {', '.join(dict.fromkeys(owners))}" if owners else "")
        )
    else:
        out.append("Явных поручений в записи не обнаружено.")
    out.append("Полный протокол см. в транскрипте. ")
    return out


def summarize(blocks: list[dict], assignments: list[dict], llm) -> dict:
    if llm.available:
        try:
            return {"summary": summarize_llm(blocks, llm), "mode": "llm"}
        except Exception as e:
            print(f"[summarize] LLM недоступен, fallback: {e}")
    return {"summary": summarize_rules(blocks, assignments), "mode": "rules"}