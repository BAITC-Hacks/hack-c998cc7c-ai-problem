"""Conservative local extractor; unsupported forms remain review questions."""

import re
from datetime import date
from schemas import Analysis, Assignment, Evidence, Segment, Statement
from date_parser import normalize_deadline

COMMAND = re.compile(
    r"\b(поручаю|поручить|подготовь\w*|направь\w*|составь\w*|сделай\w*|предоставь\w*|необходимо|дайында\w*|әзірле\w*|жібер\w*|тапсырамын)\b",
    re.I,
)
PROPOSAL = re.compile(
    r"\b(предлагаю|может быть|может,|давайте обсудим|ұсынамын|ұсыныс)\b", re.I
)
CHANGE = re.compile(r"\b(перенес\w*|перенос\w*|ауыстыр\w*)\b", re.I)
CANCEL = re.compile(r"\b(отменя\w*|отменить|күшін жо\w*)\b", re.I)
DEADLINE = re.compile(
    r"(?:к|до|на|не позднее)\s+(?:понедельн\w*|вторн\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскрес\w*|конца\s+\w+|\d{1,2}[./]\d{1,2}(?:[./]\d{4})?)|\d{4}-\d{2}-\d{2}|(?:через|спустя)\s+(?:\d+|два|две|три|четыре|пять)\s+д\w+|(?:послезавтра|завтра|сегодня|ертең|бүгін|бүрсігүні)|(?:дүйсенбі|сейсенбі|сәрсенбі|бейсенбі|жұма|сенбі|жексенбі)\w*(?:\s+дейін)?|(?:бір|екі|үш|\d+)\s+күн(?:нен)?\s+кейін|(?:осы|келесі)\s+апта\w*",
    re.I,
)


def evidence(s: Segment, quote=None):
    return Evidence(segment_id=s.id, quote=quote or s.text, start=s.start, end=s.end)


def extract_rules(segments: list[Segment], ref: date) -> Analysis:
    result = Analysis()
    last = None
    for s in segments:
        # Keep punctuation in source; quotes are exact substrings.
        clauses = [x.strip() for x in re.split(r"(?<=[.!?])\s+", s.text) if x.strip()]
        for clause in clauses:
            ev = evidence(s, clause)
            if PROPOSAL.search(clause):
                result.decisions.append(
                    Statement(text=clause, kind="proposal", evidence=[ev])
                )
                last = None
                continue
            if CHANGE.search(clause) or CANCEL.search(clause):
                # Only an adjacent anaphoric correction with one active context is safe.
                addressed = re.match(r"^([А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]+),", clause)
                linked = re.search(
                    r"^(?:нет|жоқ)\b|это поручение|эту задачу|срок|мерзім|осы тапсырма",
                    clause,
                    re.I,
                )
                if (
                    last is not None
                    and linked
                    and (not addressed or addressed[1].lower() in ("жоқ", "нет"))
                ):
                    last.evidence.append(ev)
                    if CANCEL.search(clause):
                        last.status = "cancelled"
                    else:
                        hits = list(DEADLINE.finditer(clause))
                        last.deadline_raw = hits[-1][0] if hits else clause
                        normalized = normalize_deadline(last.deadline_raw, ref)
                        last.deadline = (
                            date.fromisoformat(normalized) if normalized else None
                        )
                        last.uncertainty.append("changed_deadline_requires_review")
                    continue
                result.questions.append(clause)
                last = None
                continue
            if COMMAND.search(clause) and not re.search(
                r"\bне\s+(?:нужно|надо|подготов|направ)|не\s+поручаю|керек емес|дайындама|әзірлеме|жіберме",
                clause,
                re.I,
            ):
                owner_match = re.match(r"^([А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]+),\s*", clause)
                owner_match = owner_match or re.search(
                    r"\b[Пп]оручаю\s+([А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]+)", clause
                )
                owner = owner_match[1] if owner_match else None
                hits = list(DEADLINE.finditer(clause))
                raw = hits[-1][0] if hits else None
                deadline = normalize_deadline(raw, ref)
                action = (
                    clause[owner_match.end() :]
                    if owner_match and owner_match.start() == 0
                    else clause
                )
                action = DEADLINE.sub("", action).strip(" .,;")
                last = Assignment(
                    action=action or clause,
                    owner=owner,
                    deadline_raw=raw,
                    deadline=deadline,
                    evidence=[ev],
                    uncertainty=["rules_limited"]
                    + ([] if owner else ["owner_not_stated"])
                    + ([] if deadline else ["deadline_unclear_or_not_stated"]),
                )
                result.assignments.append(last)
            elif re.search(
                r"\b(решили|решено|бекітілді|шешім қабылданды)\b", clause, re.I
            ):
                result.decisions.append(Statement(text=clause, evidence=[ev]))
                last = None
            elif "?" in clause:
                result.questions.append(clause)
                last = None
            else:
                last = None
    # Extractive summary, clearly identified in UI and export. No invented narrative.
    result.summary = [x.text for x in result.decisions if x.kind == "decision"]
    if not result.summary:
        result.questions.append(
            "RULES: автоматическое резюме недоступно; заполните после прослушивания."
        )
    return result
