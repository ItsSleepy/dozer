"""IV Studio leads and the CS2 hub, for commands, the morning briefing and background watches.

Leads live in the IV Studio Supabase table `leads` (service key in .env as IV_SUPABASE_KEY).
CS2 data lives in the portfolio's data/cs2.json; Dozer also triggers its refresh every 20 minutes.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp

from . import config as C
from .audit import audit

TZ = ZoneInfo(C.TZ_NAME)
SB_URL = C.get("IV_SUPABASE_URL").rstrip("/")
SB_KEY = C.get("IV_SUPABASE_KEY")
CS2_FILE = Path(C.get("CS2_DATA", "/home/sleepy/personal-portfolio/data/cs2.json"))
CS2_CRON_URL = C.get("CS2_CRON_URL", "http://127.0.0.1:3100/cs2/cron")
CS2_CRON_SECRET = C.get("CS2_CRON_SECRET")
ADMIN_URL = "https://iv-studio.net/admin"

_notify = None


def set_notifier(fn):
    global _notify
    _notify = fn


# ── leads ───────────────────────────────────────────────────────────────────

async def _leads(params: dict) -> list[dict]:
    if not SB_URL or not SB_KEY:
        raise RuntimeError("IV_SUPABASE_URL / IV_SUPABASE_KEY missing in .env")
    headers = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.get(f"{SB_URL}/rest/v1/leads", params=params, headers=headers) as r:
            if r.status != 200:
                raise RuntimeError(f"Supabase said {r.status}")
            return await r.json()


def _today() -> str:
    return datetime.now(TZ).date().isoformat()


def _fmt_day(d: str) -> str:
    return datetime.fromisoformat(d).strftime("%a %d %b")


async def _lead_state() -> dict:
    rows = await _leads({"select": "id,name,town,trade,status,score,follow_up,concept_on,concept_views,concept_last_view,contacted_at,phone",
                         "limit": "2000"})
    t = _today()
    due = sorted([l for l in rows if l["follow_up"] and l["follow_up"] <= t and l["status"] in ("contacted", "replied", "meeting")],
                 key=lambda l: l["follow_up"])
    todo = sorted([l for l in rows if l["status"] in ("new", "shortlisted")], key=lambda l: -l["score"])
    since = (datetime.now(TZ) - timedelta(hours=24)).isoformat()
    viewed = [l for l in rows if l["concept_last_view"] and l["concept_last_view"] >= since]
    talking = [l for l in rows if l["status"] in ("replied", "meeting")]
    waiting = [l for l in rows if l["status"] == "contacted"]
    won = [l for l in rows if l["status"] == "won"]
    return {"rows": rows, "due": due, "todo": todo, "viewed": viewed, "talking": talking, "waiting": waiting, "won": won}


async def leads_summary() -> str:
    try:
        s = await _lead_state()
    except Exception as e:
        return f"Couldn't read leads: {e}"
    lines = [f"**IV Studio leads** · {len(s['todo'])} to contact · {len(s['waiting'])} waiting · "
             f"{len(s['talking'])} talking · {len(s['won'])} became clients"]
    if s["due"]:
        lines.append("**Follow up:**")
        for l in s["due"][:8]:
            late = " (overdue)" if l["follow_up"] < _today() else ""
            seen = f" · opened concept {l['concept_views']}×" if l["concept_views"] else " · hasn't opened the concept"
            lines.append(f"• {l['name']}{late}{seen}")
    if s["viewed"]:
        lines.append("**Opened their concept in the last 24 h:** " + ", ".join(f"{l['name']} ({l['concept_views']}×)" for l in s["viewed"][:8]))
    if s["todo"]:
        lines.append("**Best to contact next:** " + ", ".join(f"{l['name']} ({l['score']})" for l in s["todo"][:5]))
    lines.append(f"<{ADMIN_URL}> → Leads")
    return "\n".join(lines)


async def leads_due() -> str:
    try:
        s = await _lead_state()
    except Exception as e:
        return f"Couldn't read leads: {e}"
    if not s["due"]:
        return "No follow-ups due. 👍"
    return "**Follow-ups due:**\n" + "\n".join(
        f"• {l['name']} ({l['town'] or '?'}) · due {_fmt_day(l['follow_up'])} · {l['status']}"
        + (f" · {l['phone']}" if l["phone"] else "") for l in s["due"])


async def lead_info(name: str) -> str:
    q = re.sub(r"[^\w\s'&-]", "", name).strip()
    if not q:
        return "Which lead?"
    try:
        rows = await _leads({"select": "*", "name": f"ilike.*{q}*", "limit": "5"})
    except Exception as e:
        return f"Couldn't read leads: {e}"
    if not rows:
        return f"No lead matching '{name}'."
    if len(rows) > 1:
        return "Which one? " + ", ".join(r["name"] for r in rows)
    l = rows[0]
    chk = l.get("site_check") or {}
    out = [f"**{l['name']}** · {l['trade']} · {l['town'] or '?'} · score {l['score']} · {l['status']}",
           f"Phone: {l['phone'] or '–'}" + (f" · Email: {l['email']}" if l.get("email") else ""),
           f"Website: {l['website'] or 'none'}" + (f" ({', '.join(chk.get('issues', [])[:2])})" if chk.get("issues") else ""),
           "Why: " + ", ".join(l.get("score_reasons") or [])]
    if l["concept_on"]:
        out.append(f"Concept: <https://iv-studio.net/c/{l['concept_slug']}> · opened {l['concept_views']}×")
    if l["follow_up"]:
        out.append(f"Follow up: {_fmt_day(l['follow_up'])}")
    if l.get("notes"):
        out.append("Notes: " + l["notes"].strip().replace("\n", " · ")[:300])
    return "\n".join(out)


async def leads_brief() -> str:
    """One or two lines for the morning briefing, or "" when there's nothing worth saying."""
    try:
        s = await _lead_state()
    except Exception:
        return ""
    bits = []
    if s["due"]:
        bits.append(f"{len(s['due'])} follow-up{'s' if len(s['due']) > 1 else ''} due: " + ", ".join(l["name"] for l in s["due"][:4]))
    if s["viewed"]:
        bits.append("concept opened by " + ", ".join(l["name"] for l in s["viewed"][:4]))
    if s["todo"]:
        bits.append(f"{len(s['todo'])} to contact (top: {s['todo'][0]['name']})")
    return " · ".join(bits)


async def lead_watch_loop():
    """DM when someone opens their concept page: the best moment to follow up."""
    seen: dict[int, int] = {}
    first = True
    while True:
        try:
            rows = await _leads({"select": "id,name,concept_views,status", "concept_on": "eq.true", "limit": "2000"})
            for l in rows:
                prev = seen.get(l["id"])
                seen[l["id"]] = l["concept_views"]
                if not first and l["concept_views"] > (prev or 0) and _notify:
                    n = l["concept_views"]
                    await _notify(f"👀 **{l['name']}** just opened their website concept"
                                  + (f" ({n}× now)" if n > 1 else "") + ". Good moment to follow up.")
                    audit("lead_concept_view", lead=l["name"], views=n)
            first = False
        except Exception as e:
            audit("error", where="lead_watch", error=repr(e))
        await asyncio.sleep(300)


# ── CS2 ─────────────────────────────────────────────────────────────────────

MAPS = {"de_mirage": "Mirage", "de_inferno": "Inferno", "de_dust2": "Dust II", "de_nuke": "Nuke", "de_ancient": "Ancient",
        "de_anubis": "Anubis", "de_vertigo": "Vertigo", "de_overpass": "Overpass", "de_train": "Train"}


def _cs2() -> dict:
    try:
        return json.loads(CS2_FILE.read_text())
    except Exception:
        return {"players": [], "matches": {}}


def _line(m: dict, sid: str):
    return next((p for p in m["players"] if p["id"] == sid), None)


def _match_text(m: dict, p: dict) -> str:
    res = "W" if p["won"] > p["lost"] else "L" if p["won"] < p["lost"] else "T"
    when = datetime.fromisoformat(m["finishedAt"].replace("Z", "+00:00")).astimezone(TZ).strftime("%a %d %b %H:%M")
    return (f"{res} **{MAPS.get(m['map'], m['map'])}** {p['won']}–{p['lost']} · {p['k']}/{p['d']}/{p['a']} · "
            f"{round(p['adr'])} ADR · rating {p['rating'] * 100:+.2f} · {when}")


async def cs2_summary(name: str = "") -> str:
    d = _cs2()
    if not d["players"]:
        return "No CS2 players tracked yet. Add them on isaac-dev.eu/cs2."
    if name:
        pl = next((p for p in d["players"] if name.lower() in p["name"].lower()), None)
        if not pl:
            return f"Not tracking anyone called '{name}'. Tracked: " + ", ".join(p["name"] for p in d["players"])
    else:
        pl = next((p for p in d["players"] if p.get("me")), d["players"][0])
    sid = pl["steam64"]
    ms = sorted((m for m in d["matches"].values() if _line(m, sid)), key=lambda m: m["finishedAt"], reverse=True)
    cut = (datetime.now(TZ) - timedelta(days=30)).isoformat()
    month = [m for m in ms if m["finishedAt"] >= cut]
    lines = [f"🎮 **{pl['name']}**"]
    prof = pl.get("profile") or {}
    ranks = prof.get("ranks") or {}
    rk = [f"Leetify {ranks['leetify']:+.2f}" if ranks.get("leetify") is not None else "",
          f"Premier {ranks['premier']:,}" if ranks.get("premier") else "",
          f"FACEIT {ranks['faceitElo']}" if ranks.get("faceitElo") else ""]
    if any(rk):
        lines.append(" · ".join(x for x in rk if x))
    if month:
        ls = [_line(m, sid) for m in month]
        w = sum(1 for p in ls if p["won"] > p["lost"])
        k, de = sum(p["k"] for p in ls), sum(p["d"] for p in ls)
        rating = sum(p["rating"] for p in ls) / len(ls) * 100
        lines.append(f"Last 30 days: {len(ls)} games · {w}W {len(ls) - w}L ({w / len(ls):.0%}) · K/D {k / max(de, 1):.2f} · avg rating {rating:+.2f}")
    if ms:
        lines.append("Last: " + _match_text(ms[0], _line(ms[0], sid)))
    lines.append("<https://isaac-dev.eu/cs2>")
    return "\n".join(lines)


async def cs2_loop():
    """Refresh the CS2 hub every 20 minutes and DM a one-liner when Isaac finishes a match."""
    if not CS2_CRON_SECRET:
        audit("cs2_loop_off", reason="no CS2_CRON_SECRET")
        return
    known = set(_cs2()["matches"].keys())
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
                async with s.post(CS2_CRON_URL, headers={"x-cron-secret": CS2_CRON_SECRET}) as r:
                    res = await r.json(content_type=None)
            d = _cs2()
            me = next((p for p in d["players"] if p.get("me")), None)
            new = [m for mid, m in d["matches"].items() if mid not in known]
            known = set(d["matches"].keys())
            if me and _notify:
                mine = sorted((m for m in new if _line(m, me["steam64"])), key=lambda m: m["finishedAt"])
                for m in mine[-3:]:
                    await _notify("🎮 " + _match_text(m, _line(m, me["steam64"])))
            audit("cs2_refresh", added=res.get("added"), errors=res.get("errors"))
        except Exception as e:
            audit("error", where="cs2_loop", error=repr(e))
        await asyncio.sleep(1200)


TOOLS = {"leads_summary": leads_summary, "leads_due": leads_due, "lead_info": lead_info, "cs2_summary": cs2_summary}
