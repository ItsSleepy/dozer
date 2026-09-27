"""Send a message as Dozer to a channel in a server Dozer is in (confirm-gated).
Channel/server names are matched ignoring emojis and decorations ("general" finds "🌸-·-general-·˚")."""
import re
import time

import aiohttp

from . import config as C
from .audit import audit

API = "https://discord.com/api/v10"
SERVER_ALIASES = {"bmw": "bmw", "tweakers": "tweakers", "tweaker": "tweakers"}
_cache = {"at": 0.0, "guilds": []}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


async def _get(path: str):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get(API + path, headers={"Authorization": f"Bot {C.DISCORD_TOKEN}"}) as r:
            return await r.json()


async def _guilds():
    if time.time() - _cache["at"] > 600:
        _cache.update(at=time.time(), guilds=await _get("/users/@me/guilds"))
    return _cache["guilds"]


async def resolve(server: str, channel: str):
    gs = await _guilds()
    want = SERVER_ALIASES.get(_norm(server), _norm(server))
    g = next((g for g in gs if want and want in _norm(g["name"])), None)
    if not g:
        return None, f"I'm not in a server called '{server}'. I'm in: " + ", ".join(x["name"] for x in gs)
    chans = [c for c in await _get(f"/guilds/{g['id']}/channels") if c.get("type") in (0, 5)]
    cw = _norm(channel or "general")
    c = next((c for c in chans if _norm(c["name"]) == cw), None) or \
        next((c for c in chans if cw in _norm(c["name"])), None)
    if not c:
        return None, f"No channel like '{channel}' in {g['name']}."
    return (g, c), ""


def _label(c) -> str:
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", c["name"].lower()) or c["name"]


async def describe(server: str, channel: str, text: str) -> str:
    found, err = await resolve(server, channel)
    if not found:
        return err
    g, c = found
    return f"Send to **#{_label(c)}** in **{g['name']}** as Dozer:\n> {text}"


async def send_message(server: str, text: str, channel: str = "general") -> str:
    text = (text or "").strip()
    if not text:
        return "Nothing to send."
    found, err = await resolve(server, channel)
    if not found:
        return err
    g, c = found
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.post(f"{API}/channels/{c['id']}/messages", headers={"Authorization": f"Bot {C.DISCORD_TOKEN}"},
                          json={"content": text[:1900], "allowed_mentions": {"parse": []}}) as r:
            ok = r.status in (200, 201)
            detail = "" if ok else (await r.text())[:200]
    audit("discord_send", server=g["name"], channel=c["name"], text=text, ok=ok, detail=detail)
    return f"Sent to #{_label(c)} in {g['name']}." if ok else f"Discord refused it ({detail})."
