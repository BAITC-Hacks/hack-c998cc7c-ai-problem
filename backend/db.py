"""Versioned SQLite storage. v2 tables preserve any legacy data intact."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from sqlalchemy import create_engine, text
import config
from schemas import Draft

engine = create_engine(
    "sqlite:///" + config.DB_PATH,
    connect_args={"check_same_thread": False, "timeout": 30},
)


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False)


@contextmanager
def transaction():
    with engine.connect() as c:
        c.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def init_db():
    with engine.begin() as c:
        c.exec_driver_sql("PRAGMA journal_mode=WAL")
        c.exec_driver_sql("""CREATE TABLE IF NOT EXISTS meetings_v2 (
            id INTEGER PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL,
            metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'queued',
            error TEXT, created_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
            draft TEXT NOT NULL, checkpoint TEXT, candidate TEXT, analysis_only INTEGER NOT NULL DEFAULT 0)""")
        c.exec_driver_sql("""CREATE TABLE IF NOT EXISTS versions_v2 (
            id INTEGER PRIMARY KEY, meeting_id INTEGER NOT NULL, revision INTEGER NOT NULL,
            created_at TEXT NOT NULL, snapshot TEXT NOT NULL, UNIQUE(meeting_id,revision))""")
        c.exec_driver_sql("""CREATE TABLE IF NOT EXISTS audit_v2 (
            id INTEGER PRIMARY KEY, meeting_id INTEGER NOT NULL, ts TEXT NOT NULL,
            action TEXT NOT NULL, before_json TEXT, after_json TEXT)""")


def audit(c, mid, action, before=None, after=None):
    c.execute(
        text(
            "INSERT INTO audit_v2(meeting_id,ts,action,before_json,after_json) VALUES (:m,:t,:a,:b,:n)"
        ),
        dict(m=mid, t=now(), a=action, b=encode(before), n=encode(after)),
    )


def create_meeting(filename, path, meta):
    with transaction() as c:
        result = c.execute(
            text(
                "INSERT INTO meetings_v2(filename,path,metadata,created_at,draft) VALUES (:f,:p,:m,:t,:d)"
            ),
            dict(
                f=filename,
                p=str(path),
                m=encode(meta),
                t=now(),
                d=Draft().model_dump_json(),
            ),
        )
        mid = result.lastrowid
        audit(c, mid, "uploaded")
        return mid


def unpack(row):
    m = dict(row)
    for key in ("metadata", "draft", "checkpoint", "candidate"):
        m[key] = json.loads(m[key]) if m[key] else None
    return m


def get_meeting(mid):
    with engine.connect() as c:
        row = (
            c.execute(text("SELECT * FROM meetings_v2 WHERE id=:id"), {"id": mid})
            .mappings()
            .first()
        )
        if not row:
            return None
        m = unpack(row)
        m["versions"] = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT id,revision,created_at FROM versions_v2 WHERE meeting_id=:m ORDER BY id DESC"
                ),
                {"m": mid},
            ).mappings()
        ]
        m["events"] = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT id,ts,action FROM audit_v2 WHERE meeting_id=:m ORDER BY id"
                ),
                {"m": mid},
            ).mappings()
        ]
        return m


def list_meetings():
    with engine.connect() as c:
        return [
            dict(
                id=r.id,
                filename=r.filename,
                metadata=json.loads(r.metadata),
                status=r.status,
                stage=r.stage,
                error=r.error,
            )
            for r in c.execute(
                text(
                    "SELECT id,filename,metadata,status,stage,error FROM meetings_v2 ORDER BY id DESC"
                )
            )
        ]


def claim():
    with transaction() as c:
        row = (
            c.execute(
                text(
                    "SELECT * FROM meetings_v2 WHERE status='queued' ORDER BY id LIMIT 1"
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        c.execute(
            text("UPDATE meetings_v2 SET status='processing',error=NULL WHERE id=:id"),
            {"id": row["id"]},
        )
        audit(c, row["id"], "started")
        return unpack(row)


def recover():
    with transaction() as c:
        c.execute(
            text(
                "UPDATE meetings_v2 SET status='queued',stage='recovered' WHERE status='processing'"
            )
        )


def stage(mid, stage, checkpoint=None):
    with transaction() as c:
        c.execute(
            text("UPDATE meetings_v2 SET stage=:s WHERE id=:m"), dict(m=mid, s=stage)
        )
        if checkpoint is not None:
            c.execute(
                text("UPDATE meetings_v2 SET checkpoint=:d WHERE id=:m"),
                dict(m=mid, d=encode(checkpoint)),
            )
        audit(c, mid, stage)


def finish(mid, draft, analysis_only=False):
    with transaction() as c:
        field = "candidate" if analysis_only else "draft"
        c.execute(
            text(
                f"UPDATE meetings_v2 SET {field}=:d,status='done',stage='review',revision=revision+1 WHERE id=:m"
            ),
            dict(m=mid, d=encode(draft)),
        )
        audit(c, mid, "candidate_ready" if analysis_only else "draft_ready")


def fail(mid, message):
    with transaction() as c:
        row = c.execute(
            text("SELECT draft,checkpoint FROM meetings_v2 WHERE id=:m"), dict(m=mid)
        ).first()
        if row and row.checkpoint:
            draft = json.loads(row.draft)
            if not draft["transcript"]:
                draft["transcript"] = json.loads(row.checkpoint)
                c.execute(
                    text(
                        "UPDATE meetings_v2 SET draft=:d,revision=revision+1 WHERE id=:m"
                    ),
                    dict(m=mid, d=encode(draft)),
                )
        c.execute(
            text("UPDATE meetings_v2 SET status='error',error=:e WHERE id=:m"),
            dict(m=mid, e=message),
        )
        audit(c, mid, "processing_failed")


def editable(c, mid, revision):
    row = (
        c.execute(text("SELECT * FROM meetings_v2 WHERE id=:m"), dict(m=mid))
        .mappings()
        .first()
    )
    if not row:
        raise LookupError("Meeting not found")
    m = unpack(row)
    if m["status"] in ("queued", "processing") or revision != m["revision"]:
        raise ValueError(
            "Meeting is processing or revision is stale; reload before saving"
        )
    return m


def save_draft(mid, revision, draft):
    with transaction() as c:
        m = editable(c, mid, revision)
        before = m["draft"]
        previous = {a["id"]: a for a in before["assignments"]}
        for a in draft["assignments"]:
            old = previous.get(a["id"])
            if old:
                a["origin"] = old["origin"]
                substantive = (
                    "action",
                    "owner",
                    "expected_result",
                    "deadline",
                    "deadline_raw",
                    "evidence",
                )
                if any(old[k] != a[k] for k in substantive):
                    a["review"] = "needs_review"
            else:
                a["origin"] = "manual"
                a["review"] = "needs_review"
        # The source edit invalidates ALL derived output, including summary/decisions.
        if before["transcript"] != draft["transcript"]:
            draft["reviewed"] = False
            for a in draft["assignments"]:
                a["review"] = "needs_review"
                a["uncertainty"] = list(
                    dict.fromkeys(a["uncertainty"] + ["source_changed"])
                )
        c.execute(
            text("UPDATE meetings_v2 SET draft=:d,revision=revision+1 WHERE id=:m"),
            dict(m=mid, d=encode(draft)),
        )
        audit(c, mid, "draft_edited", before, draft)


def approve(mid, revision):
    from schemas import validate_evidence

    with transaction() as c:
        m = editable(c, mid, revision)
        draft = Draft.model_validate(m["draft"])
        if not draft.transcript or not draft.reviewed:
            raise ValueError("Review the transcript, summary and decisions first")
        validate_evidence(draft, draft.transcript)
        for a in draft.assignments:
            if a.review != "confirmed":
                raise ValueError("Confirm every assignment first")
            for field in ("owner", "deadline", "expected_result"):
                if getattr(a, field) is None and field not in a.unspecified:
                    raise ValueError(
                        "Confirm missing fields as not stated in the recording"
                    )
        existing = c.execute(
            text("SELECT id FROM versions_v2 WHERE meeting_id=:m AND revision=:r"),
            dict(m=mid, r=revision),
        ).scalar()
        if existing:
            return existing
        snapshot = dict(metadata=m["metadata"], draft=m["draft"], revision=revision)
        result = c.execute(
            text(
                "INSERT INTO versions_v2(meeting_id,revision,created_at,snapshot) VALUES (:m,:r,:t,:s)"
            ),
            dict(m=mid, r=revision, t=now(), s=encode(snapshot)),
        )
        audit(c, mid, "version_approved")
        return result.lastrowid


def version(mid, vid):
    with engine.connect() as c:
        value = c.execute(
            text("SELECT snapshot FROM versions_v2 WHERE id=:v AND meeting_id=:m"),
            dict(m=mid, v=vid),
        ).scalar()
        return json.loads(value) if value else None


def enqueue(mid, revision, analysis_only):
    with transaction() as c:
        m = editable(c, mid, revision)
        if not analysis_only and m["draft"]["transcript"]:
            raise ValueError("Use reanalysis to preserve edited transcript")
        if analysis_only and not m["draft"]["transcript"]:
            raise ValueError("No transcript to analyze")
        checkpoint = m["draft"]["transcript"] if analysis_only else m["checkpoint"]
        c.execute(
            text(
                "UPDATE meetings_v2 SET status='queued',stage='queued',error=NULL,analysis_only=:a,checkpoint=:p WHERE id=:m"
            ),
            dict(m=mid, a=int(analysis_only), p=encode(checkpoint)),
        )
        audit(c, mid, "reanalysis_requested" if analysis_only else "retry_requested")


def apply_candidate(mid, revision):
    with transaction() as c:
        m = editable(c, mid, revision)
        if not m["candidate"]:
            raise ValueError("No candidate")
        # Explicit replacement is initiated by the review UI; original remains in audit and versions.
        c.execute(
            text(
                "UPDATE meetings_v2 SET draft=candidate,candidate=NULL,revision=revision+1 WHERE id=:m"
            ),
            dict(m=mid),
        )
        audit(c, mid, "candidate_explicitly_applied", m["draft"], m["candidate"])
