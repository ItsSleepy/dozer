"""Reminders: natural-ish time parsing, repeating reminders, persistent in data/reminders.json."""
import asyncio
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config as C
from .audit import audit

TZ = ZoneInfo(C.TZ_NAME)
FILE = C.ROOT / "data" / "reminders.json"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_SHORT = {d[:3]: i for i, d in enumerate(DAYS)} | {d: i for i, d in enumerate(DAYS)}
UNITS = {"m": 1, "min": 1, "mins": 1, "minute": 1, "minutes": 1, "h": 60, "hr": 60, "hrs": 60, "hour": 60,
         "hours": 60, "d": 1440, "day": 1440, "days": 1440}
_deliver = None      # set by bot.py: async fn(reminder, late: bool)


def set_deliver(fn):
    global _deliver
    _deliver = fn


# ── storage ─────────────────────────────────────────────────────────────────

def load() -> list:
    try:
        return json.loads(FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(items: list):
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False))


# ── parsing ─────────────────────────────────────────────────────────────────

def _time(s: str):
    s = s.strip().lower()
    if s in ("noon", "midday"):
        return 12, 0
    if s == "midnight":
        return 0, 0
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", s)
    if not m:
        return None
    h, mi, ap = int(m[1]), int(m[2] or 0), m[3]
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return (h, mi) if h < 24 and mi < 60 else None


def parse_when(phrase: str, now: datetime | None = None):
    """Returns (due datetime, repeat) or None. repeat: None | 'daily' | 'weekdays' | 'weekly:<n>'."""
    now = now or datetime.now(TZ)
    p = re.sub(r"\s+", " ", phrase.strip().lower().replace(",", " "))

    # relative: in 20m / in 1h 30m / in 2 hours
    if p.startswith("in "):
        pairs = re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", p[3:])
        mins = sum(float(n) * UNITS[u] for n, u in pairs if u in UNITS)
        return (now + timedelta(minutes=mins), None) if mins > 0 else None

    repeat = None
    m = re.match(r"every (day|weekday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b ?(.*)$", p)
    if m:
        what, p = m[1], m[2]
        repeat = "daily" if what == "day" else "weekdays" if what == "weekday" else f"weekly:{DAY_SHORT[what]}"

    tm = re.search(r"(?:at )?(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon|midday|midnight)\s*$", p)
    hm = _time(tm[1]) if tm else None
    day_part = p[:tm.start()].strip() if tm else p.strip()
    day_part = re.sub(r"^on ", "", day_part).strip()

    base = now.date()
    default_hm = (9, 0)
    if day_part in ("", "today"):
        pass
    elif day_part == "tonight":
        default_hm = (20, 0)
    elif day_part == "tomorrow":
        base += timedelta(days=1)
    elif day_part in DAY_SHORT:
        delta = (DAY_SHORT[day_part] - now.weekday()) % 7
        base += timedelta(days=delta or (0 if hm and datetime.combine(base, datetime.min.time()).replace(
            hour=hm[0], minute=hm[1], tzinfo=TZ) > now else 7))
    elif re.fullmatch(r"\d{1,2}/\d{1,2}(/\d{2,4})?", day_part):
        d, mo, *y = day_part.split("/")
        yr = int(y[0]) + (2000 if y and len(y[0]) == 2 else 0) if y else now.year
        try:
            base = datetime(yr, int(mo), int(d)).date()
        except ValueError:
            return None
        if not y and base < now.date():
            base = base.replace(year=now.year + 1)
    elif repeat and day_part == "":
        pass
    else:
        return None

    if not hm and not day_part and not repeat:
        return None
    h, mi = hm or default_hm
    due = datetime(base.year, base.month, base.day, h, mi, tzinfo=TZ)
    if repeat:
        due = _next_repeat(repeat, now, (h, mi))
    elif due <= now:
        if day_part in ("", "today", "tonight") and hm:
            due += timedelta(days=1)          # "at 9" when it's already 10 -> tomorrow 9
        else:
            return None
    return due, repeat


def _matches(repeat: str, dt: datetime) -> bool:
    if repeat == "daily":
        return True
    if repeat == "weekdays":
        return dt.weekday() < 5
    return dt.weekday() == int(repeat.split(":")[1])


def _next_repeat(repeat: str, after: datetime, hm) -> datetime:
    cand = after.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if cand <= after:
        cand += timedelta(days=1)
    while not _matches(repeat, cand):
        cand += timedelta(days=1)
    return cand


def split_request(text: str):
    """'remind me at 6 to call mum' / 'remind me to call mum at 6' -> (when, what)."""
    t = re.sub(r"^(please )?remind me\s*", "", text.strip(), flags=re.I)
    m = re.match(r"^to (.+?) ((?:in|at|on|tomorrow|tonight|today|every)\b.*)$", t, re.I)
    if m:
        return m[2], m[1]
    m = re.match(r"^(.+?) (?:to|that|about) (.+)$", t, re.I)
    if m:
        return m[1], m[2]
    return None


# ── operations ──────────────────────────────────────────────────────────────

def _fmt(dt: datetime) -> str:
    now = datetime.now(TZ)
    if dt.date() == now.date():
        return f"today {dt:%H:%M}"
    if dt.date() == (now + timedelta(days=1)).date():
        return f"tomorrow {dt:%H:%M}"
    return dt.strftime("%a %d %b %H:%M")


def _rep_label(r):
    rep = r.get("repeat")
    if not rep:
        return ""
    return " (every day)" if rep == "daily" else " (weekdays)" if rep == "weekdays" else \
        f" (every {DAYS[int(rep.split(':')[1])].capitalize()})"


async def set_reminder(when: str, text: str) -> str:
    parsed = parse_when(when)
    if not parsed:
        return (f"Couldn't understand the time '{when}'. Try: in 20m · at 18:00 · tomorrow at 9 · "
                "on friday at 17:30 · on 28/09 at 10 · every day at 22:00")
    due, repeat = parsed
    items = load()
    rid = max((r["id"] for r in items), default=0) + 1
    r = {"id": rid, "text": text.strip(), "due": due.isoformat(timespec="seconds"), "repeat": repeat,
         "created": datetime.now(TZ).isoformat(timespec="minutes"), "done": False}
    items.append(r)
    save(items)
    audit("reminder_set", reminder=r, phrase=when)
    return f"⏰ Reminder `#{rid}` set for {_fmt(due)}{_rep_label(r)}: {r['text']}"


async def list_reminders() -> str:
    items = sorted((r for r in load() if not r["done"]), key=lambda r: r["due"])
    if not items:
        return "No upcoming reminders."
    return "**Reminders**\n" + "\n".join(
        f"`#{r['id']}` {_fmt(datetime.fromisoformat(r['due']))}{_rep_label(r)} — {r['text']}" for r in items) + \
        "\n`cancel reminder <id>` · `snooze <id> 10m`"


async def cancel_reminder(rid: int) -> str:
    items = load()
    for r in items:
        if r["id"] == int(rid) and not r["done"]:
            r["done"] = True
            save(items)
            audit("reminder_cancel", id=rid)
            return f"Cancelled reminder `#{rid}`: {r['text']}"
    return f"No active reminder #{rid}."


async def snooze(rid: int, minutes: int = 10) -> str:
    items = load()
    for r in items:
        if r["id"] == int(rid):
            due = datetime.now(TZ) + timedelta(minutes=int(minutes))
            if r.get("repeat"):          # snoozing a repeating one creates a one-off copy
                nid = max(x["id"] for x in items) + 1
                items.append({**r, "id": nid, "due": due.isoformat(timespec="seconds"), "repeat": None, "done": False})
                rid = nid
            else:
                r.update(due=due.isoformat(timespec="seconds"), done=False)
            save(items)
            audit("reminder_snooze", id=rid, minutes=minutes)
            return f"Snoozed `#{rid}` until {_fmt(due)}."
    return f"No reminder #{rid}."


def today_lines() -> list:
    now = datetime.now(TZ)
    return [f"{datetime.fromisoformat(r['due']):%H:%M} — {r['text']}"
            for r in sorted(load(), key=lambda r: r["due"])
            if not r["done"] and datetime.fromisoformat(r["due"]).date() == now.date()]


# ── delivery loop ───────────────────────────────────────────────────────────

async def loop():
    audit("reminders_start", active=sum(1 for r in load() if not r["done"]))
    while True:
        now = datetime.now(TZ)
        items = load()
        changed = False
        for r in items:
            if r["done"]:
                continue
            due = datetime.fromisoformat(r["due"])
            if due > now:
                continue
            late = (now - due) > timedelta(minutes=2)
            if r.get("repeat"):
                r["due"] = _next_repeat(r["repeat"], now, (due.hour, due.minute)).isoformat(timespec="minutes")
            else:
                r["done"] = True
            changed = True
            audit("reminder_fire", id=r["id"], text=r["text"], late=late)
            if _deliver:
                asyncio.create_task(_deliver(dict(r), late))
        if changed:
            save(items)
        await asyncio.sleep(15)
