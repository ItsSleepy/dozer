"""Long-term memory: things Isaac explicitly tells Dozer to remember.
SQLite + FTS5 (porter stemming) in data/memory.db. Works without the brain."""
import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config as C
from .audit import audit

TZ = ZoneInfo(C.TZ_NAME)
DB = C.ROOT / "data" / "memory.db"
STOP = set("""a an the and or but if then so to of in on at for with about from by is are was were be been am i me my
mine you your it its this that these those what when where who whom which how why do does did done have has had
say said tell told remember recall know forget please dozer can could would should will just any some there here
again also than too very not no yes up out into over under""".split())


def _db() -> sqlite3.Connection:
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL, created TEXT NOT NULL)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(text, content='notes', content_rowid='id', "
              "tokenize='porter unicode61')")
    c.execute("CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN "
              "INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text); END")
    c.execute("CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN "
              "INSERT INTO notes_fts(notes_fts, rowid, text) VALUES ('delete', old.id, old.text); END")
    return c


def _fts_query(text: str) -> str:
    words = [w for w in re.findall(r"[a-zA-Z0-9€£$]+", text.lower()) if w not in STOP and len(w) > 1]
    return " OR ".join(f'"{w}"*' for w in dict.fromkeys(words))


def search(text: str, limit: int = 5) -> list:
    q = _fts_query(text)
    if not q:
        return []
    with _db() as c:
        return c.execute("SELECT n.id, n.text, n.created FROM notes_fts f JOIN notes n ON n.id = f.rowid "
                         "WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT ?", (q, limit)).fetchall()


def _fmt(row) -> str:
    rid, text, created = row
    return f"`#{rid}` {text} *({datetime.fromisoformat(created):%d %b %Y})*"


# ── tools ───────────────────────────────────────────────────────────────────

async def remember(text: str) -> str:
    text = re.sub(r"^(that|this:?)\s+", "", text.strip(), flags=re.I).strip()
    if not text:
        return "Nothing to remember."
    with _db() as c:
        dup = c.execute("SELECT id FROM notes WHERE lower(text) = lower(?)", (text,)).fetchone()
        if dup:
            return f"Already remembered as `#{dup[0]}`."
        rid = c.execute("INSERT INTO notes (text, created) VALUES (?, ?)",
                        (text, datetime.now(TZ).isoformat(timespec="minutes"))).lastrowid
    audit("memory_add", id=rid, text=text)
    return f"🧠 Remembered `#{rid}`: {text}"


async def recall(query: str) -> str:
    rows = search(query, 8)
    audit("memory_recall", query=query, hits=[r[0] for r in rows])
    if not rows:
        return f"Nothing in memory about '{query}'."
    return "\n".join(_fmt(r) for r in rows)


async def forget(rid: int) -> str:
    with _db() as c:
        row = c.execute("SELECT id, text, created FROM notes WHERE id = ?", (int(rid),)).fetchone()
        if not row:
            return f"No memory #{rid}."
        c.execute("DELETE FROM notes WHERE id = ?", (int(rid),))
    audit("memory_forget", id=rid, text=row[1])
    return f"Forgot `#{rid}`: {row[1]}"


async def list_memories(n: int = 15) -> str:
    with _db() as c:
        rows = c.execute("SELECT id, text, created FROM notes ORDER BY id DESC LIMIT ?", (max(1, min(int(n), 50)),)).fetchall()
        total = c.execute("SELECT count(*) FROM notes").fetchone()[0]
    if not rows:
        return "Memory is empty. Try: `remember that …`"
    return f"**Memory** ({total} total, newest first)\n" + "\n".join(_fmt(r) for r in rows) + \
        "\n`forget <id>` · `what did I say about …`"


def context_for(text: str, limit: int = 4) -> str:
    """Relevant memories to give the brain alongside a question (empty if none)."""
    rows = search(text, limit)
    if not rows:
        return ""
    audit("memory_context", hits=[r[0] for r in rows])
    return "Things Isaac asked you to remember (use only if relevant):\n" + \
        "\n".join(f"- #{r[0]} ({datetime.fromisoformat(r[2]):%d %b %Y}): {r[1]}" for r in rows)


def matches_for_forget(text: str) -> list:
    return search(text, 5)
