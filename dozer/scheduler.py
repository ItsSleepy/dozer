"""Scheduled tasks (Dozer's version of Claude's scheduled tasks).
A job = a schedule + a command Isaac could type himself. Isaac confirms once when creating the job;
scheduled runs then execute without asking. Jobs live in data/schedules.json."""
import asyncio
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config as C
from .audit import audit

TZ = ZoneInfo(C.TZ_NAME)
FILE = C.ROOT / "data" / "schedules.json"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SPEC_RE = re.compile(r"^(daily (\d{1,2}):(\d{2})|weekly (mon|tue|wed|thu|fri|sat|sun) (\d{1,2}):(\d{2})|every (\d+)([hm]))$", re.I)

_runner = None      # set by bot.py: async fn(job) -> None


def set_runner(fn):
    global _runner
    _runner = fn


def load() -> list:
    try:
        return json.loads(FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(jobs: list):
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(jobs, indent=2, ensure_ascii=False))


def valid_spec(spec: str) -> bool:
    m = SPEC_RE.match(spec.strip())
    if not m:
        return False
    if m[7]:
        mins = int(m[7]) * (60 if m[8].lower() == "h" else 1)
        return mins >= 15
    h, mi = (m[2], m[3]) if m[2] else (m[5], m[6])
    return int(h) < 24 and int(mi) < 60


def next_run(spec: str, after: datetime) -> datetime:
    m = SPEC_RE.match(spec.strip())
    if m[7]:
        step = timedelta(hours=int(m[7])) if m[8].lower() == "h" else timedelta(minutes=int(m[7]))
        return after + step
    h, mi = (int(m[2]), int(m[3])) if m[2] else (int(m[5]), int(m[6]))
    cand = after.replace(hour=h, minute=mi, second=0, microsecond=0)
    if m[4]:
        cand += timedelta(days=(DAYS.index(m[4].lower()) - cand.weekday()) % 7)
        if cand <= after:
            cand += timedelta(days=7)
    elif cand <= after:
        cand += timedelta(days=1)
    return cand


def add(spec: str, command: str) -> dict:
    jobs = load()
    jid = max((j["id"] for j in jobs), default=0) + 1
    now = datetime.now(TZ)
    job = {"id": jid, "spec": spec.lower(), "command": command, "enabled": True,
           "created": now.isoformat(timespec="minutes"), "next": next_run(spec, now).isoformat(timespec="minutes"),
           "last": None, "last_result": None}
    jobs.append(job)
    save(jobs)
    audit("schedule_add", job=job)
    return job


def remove(jid: int) -> bool:
    jobs = load()
    keep = [j for j in jobs if j["id"] != jid]
    save(keep)
    audit("schedule_remove", id=jid, removed=len(keep) != len(jobs))
    return len(keep) != len(jobs)


def set_enabled(jid: int, on: bool) -> bool:
    jobs = load()
    for j in jobs:
        if j["id"] == jid:
            j["enabled"] = on
            if on:
                j["next"] = next_run(j["spec"], datetime.now(TZ)).isoformat(timespec="minutes")
            save(jobs)
            audit("schedule_toggle", id=jid, enabled=on)
            return True
    return False


def describe() -> str:
    jobs = load()
    if not jobs:
        return "No scheduled tasks. Add one: `schedule daily 04:00 backup`"
    lines = []
    for j in jobs:
        nxt = datetime.fromisoformat(j["next"]).strftime("%a %d %b %H:%M") if j["enabled"] else "paused"
        last = f", last {datetime.fromisoformat(j['last']).strftime('%d %b %H:%M')}" if j["last"] else ""
        lines.append(f"`#{j['id']}` {j['spec']} → `{j['command']}` — next {nxt}{last}")
    return "**Scheduled tasks**\n" + "\n".join(lines) + "\n`unschedule <id>` · `pause <id>` · `resume <id>`"


async def loop():
    audit("scheduler_start", jobs=len(load()))
    while True:
        await asyncio.sleep(20)
        now = datetime.now(TZ)
        jobs = load()
        changed = False
        for j in jobs:
            if not j["enabled"] or datetime.fromisoformat(j["next"]) > now:
                continue
            j["last"] = now.isoformat(timespec="minutes")
            j["next"] = next_run(j["spec"], now).isoformat(timespec="minutes")
            changed = True
            audit("schedule_run", id=j["id"], command=j["command"])
            try:
                j["last_result"] = "ok"
                if _runner:
                    asyncio.create_task(_runner(j))
            except Exception as e:
                j["last_result"] = repr(e)
                audit("error", where="scheduler", id=j["id"], error=repr(e))
        if changed:
            save(jobs)
