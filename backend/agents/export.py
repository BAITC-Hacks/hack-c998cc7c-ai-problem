"""Exports from an explicit immutable version or a visibly marked draft."""

import io
from pathlib import Path
from xml.sax.saxutils import escape
from docx import Document
from docx.shared import Cm, Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate
import config

LETTERS = "ӘҒҚҢӨҰҮҺІәғқңөұүһі"


def font_path():
    choices = [
        config.PDF_FONT,
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for p in choices:
        if p and Path(p).is_file():
            f = TTFont("Khattama", p)
            if all(ord(ch) in f.face.charToGlyph for ch in LETTERS):
                pdfmetrics.registerFont(f)
                return p
    raise ValueError(
        "PDF_FONT_MISSING: set PDF_FONT to a TTF containing Kazakh Cyrillic glyphs"
    )


def ts(sec):
    return f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"


def sections(snapshot, approved=False, include_transcript=True):
    m, d = snapshot["metadata"], snapshot["draft"]
    yield 0, m["title"]
    yield (
        0,
        "Хаттама AI · "
        + ("Бекітілген нұсқа / Утверждённая версия" if approved else "ЖОБА / ЧЕРНОВИК"),
    )
    yield 0, f"{m['meeting_at']} · {m['timezone']} · v{snapshot['revision']}"
    yield 0, "Қатысушылар / Участники: " + (", ".join(m["participants"]) or "—")
    yield (
        0,
        "Режим: "
        + m["mode"]
        + (
            " · RULES: ограниченный извлекатель, резюме только из явных решений"
            if m["mode"] == "RULES"
            else ""
        ),
    )
    yield (
        0,
        "Бекіту — осы қолданбадағы тексеру; электрондық қолтаңба емес. / Утверждение не является электронной подписью.",
    )
    yield 1, "Түйін / Резюме"
    for s in d["summary"]:
        yield 0, s
    yield 1, "Шешімдер мен ұсыныстар / Решения и предложения"
    for item in d["decisions"]:
        yield 0, f"[{item['kind']}] {item['text']}"
        for e in item["evidence"]:
            yield 0, f"[{ts(e['start'])}–{ts(e['end'])}] «{e['quote']}»"
    yield 1, "Тапсырмалар / Поручения"
    for i, a in enumerate(d["assignments"], 1):
        yield 0, f"{i}. {a['action']}"
        yield (
            0,
            f"Орындаушы / Исполнитель: {a['owner'] or 'не указан'} · Срок: {a['deadline'] or 'не указан'} · Исходный срок: {a['deadline_raw'] or '—'}",
        )
        yield (
            0,
            f"Результат: {a['expected_result'] or 'не указан'} · {a['status']} · {a['review']} · {a['origin']}",
        )
        if a["uncertainty"]:
            yield 0, "Требует внимания: " + ", ".join(a["uncertainty"])
        if a["unspecified"]:
            yield (
                0,
                "Подтверждено «в записи не указано»: " + ", ".join(a["unspecified"]),
            )
        for e in a["evidence"]:
            yield (
                0,
                f"[{ts(e['start'])}–{ts(e['end'])}] «{e['quote']}» ({e['segment_id']})",
            )
    yield 1, "Ашық сұрақтар / Открытые вопросы"
    for q in d["questions"]:
        yield 0, q
    if include_transcript:
        yield 1, "Транскрипт"
        for s in d["transcript"]:
            yield (
                0,
                f"[{ts(s['start'])}–{ts(s['end'])}] {s['speaker'] or 'Сөйлеуші белгісіз / Говорящий неизвестен'}: {s['text']}",
            )


def build_docx(snapshot, approved=False, include_transcript=True):
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin = section.right_margin = Cm(2)
    for i, (level, content) in enumerate(
        sections(snapshot, approved, include_transcript)
    ):
        if i == 0:
            doc.add_paragraph(content, "Title")
        elif level:
            doc.add_heading(content, level=1)
        else:
            doc.add_paragraph(content)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def build_pdf(snapshot, approved=False, include_transcript=True):
    font_path()
    body = ParagraphStyle(
        "body",
        fontName="Khattama",
        fontSize=10,
        leading=14,
        spaceAfter=6,
        splitLongWords=True,
    )
    heading = ParagraphStyle(
        "heading",
        parent=body,
        fontSize=13,
        leading=17,
        spaceBefore=12,
        keepWithNext=True,
    )
    title = ParagraphStyle("title", parent=body, fontSize=18, leading=23, spaceAfter=12)
    story = []
    for i, (level, content) in enumerate(
        sections(snapshot, approved, include_transcript)
    ):
        story.append(
            Paragraph(
                escape(content).replace("\n", "<br/>"),
                title if i == 0 else heading if level else body,
            )
        )
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=56, rightMargin=56, topMargin=48, bottomMargin=48
    )

    def footer(canvas, doc):
        canvas.setFont("Khattama", 8)
        canvas.drawRightString(A4[0] - 56, 28, str(doc.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf
