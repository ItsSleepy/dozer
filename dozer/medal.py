"""Medal clips via Medal's website API using Isaac's own session (unofficial, experimental).
Privacy: 0/1 = public/unlisted, 4 = anyone with the link (most clips), 5 = private (link won't work for others)."""
import time
from datetime import datetime

import aiohttp

from . import config as C
from .audit import audit

API = "https://medal.tv/api/content"
BMW_GUILD = "1248973514506113104"
DEFAULT_CHANNEL = "faze_clipz"
GAME_ALIASES = {"cs": "counter-strike 2", "cs2": "counter-strike 2", "counter": "counter-strike 2",
                "mc": "minecraft", "fh": "forza", "fn": "fortnite", "screen": "screen recording"}
SHAREABLE = {0, 1, 4}
_cache = {"at": 0.0, "clips": []}


class MedalAuthError(Exception):
    pass


def _headers():
    return {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
            "Medal-User-Agent": "Medal-web/1.0", "X-Authentication": C.get("MEDAL_SESSION")}


async def fetch(pages: int = 3) -> list:
    if time.time() - _cache["at"] < 120 and _cache["clips"]:
        return _cache["clips"]
    if not C.get("MEDAL_SESSION"):
        raise MedalAuthError("MEDAL_SESSION is not set in .env")
    uid = C.get("MEDAL_USER_ID", "42525252")
    clips = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        for i in range(pages):
            url = f"{API}?userId={uid}&limit=100&offset={i * 100}&sortDirection=DESC"
            async with s.get(url, headers=_headers()) as r:
                if r.status == 401:
                    raise MedalAuthError("Medal session expired")
                page = await r.json()
            clips += page
            if len(page) < 100:
                break
    clips.sort(key=lambda c: c.get("created", 0), reverse=True)
    _cache.update(at=time.time(), clips=clips)
    return clips


def _game(c) -> str:
    return (c.get("category") or {}).get("alternativeName") or "?"


def _filter(clips, game: str):
    if not game:
        return clips
    g = GAME_ALIASES.get(game.lower().strip(), game.lower().strip())
    return [c for c in clips if g in _game(c).lower()]


def _line(i, c) -> str:
    dt = datetime.fromtimestamp(c["created"] / 1000)
    when = dt.strftime("%d %b %H:%M") if dt.year == datetime.now().year else dt.strftime("%d %b %Y")
    title = c.get("contentTitle") or "Untitled"
    lock = " 🔒private" if c.get("privacy") == 5 else ""
    return f"`{i}` {when} · {_game(c)} · {title} · {round(c.get('videoLengthSeconds', 0))}s{lock}"


async def medal_clips(game: str = "", n: int = 5) -> str:
    try:
        clips = _filter(await fetch(), game)
    except MedalAuthError as e:
        return f"Medal: {e}. Grab a fresh X-Authentication from medal.tv DevTools into MEDAL_SESSION."
    if not clips:
        return f"No clips found{' for ' + game if game else ''}."
    n = max(1, min(int(n), 15))
    return "\n".join(_line(i + 1, c) for i, c in enumerate(clips[:n])) + \
        "\nPost one: `post clip <number> [game] [to <channel>]`"


async def _channel_id(name: str) -> tuple[str, str] | None:
    name = (name or DEFAULT_CHANNEL).lstrip("#").lower()
    if name in ("clips", "clip"):
        name = DEFAULT_CHANNEL
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{BMW_GUILD}/channels",
                         headers={"Authorization": f"Bot {C.DISCORD_TOKEN}"}) as r:
            chans = [c for c in await r.json() if c.get("type") in (0, 5)]
    exact = [c for c in chans if c["name"].lower() == name]
    part = exact or [c for c in chans if name in c["name"].lower()]
    return (part[0]["id"], part[0]["name"]) if part else None


async def post_clip(which: int = 1, game: str = "", channel: str = "", note: str = "") -> str:
    try:
        clips = _filter(await fetch(), game)
    except MedalAuthError as e:
        return f"Medal: {e}. Grab a fresh X-Authentication from medal.tv DevTools into MEDAL_SESSION."
    which = max(1, int(which))
    if len(clips) < which:
        return f"Only {len(clips)} clip(s){' for ' + game if game else ''}."
    clip = clips[which - 1]
    if clip.get("privacy") not in SHAREABLE:
        return "That clip is private on Medal, so nobody else could open it. Change it in Medal first, or pick another."
    chan = await _channel_id(channel)
    if not chan:
        return f"Couldn't find a channel matching '{channel}' in the BMW server."
    url = clip.get("contentShareUrl") or f"https://medal.tv/clips/{clip['contentId']}"
    content = f"{note}\n{url}".strip()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.post(f"https://discord.com/api/v10/channels/{chan[0]}/messages",
                          headers={"Authorization": f"Bot {C.DISCORD_TOKEN}"}, json={"content": content}) as r:
            ok = r.status in (200, 201)
            detail = "" if ok else (await r.text())[:200]
    audit("medal_post", clip=clip["contentId"], channel=chan[1], ok=ok, detail=detail)
    return f"Posted to #{chan[1]}: {_line(which, clip)}" if ok else f"Discord refused the post ({detail})."


async def describe_pick(which: int = 1, game: str = "", channel: str = "") -> str:
    """Used for the confirmation prompt, so Isaac sees exactly which clip goes where."""
    try:
        clips = _filter(await fetch(), game)
        clip = clips[max(1, int(which)) - 1]
        return f"Post this clip to #{(channel or DEFAULT_CHANNEL).lstrip('#')}?\n{_line(which, clip)}\n{clip.get('contentShareUrl', '')}"
    except Exception:
        return f"Post clip {which}{' (' + game + ')' if game else ''} to #{channel or DEFAULT_CHANNEL}?"
