"""Dozer v1 — Discord DM interface, confirmations, watchdog, briefing, webhook."""
import asyncio
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
import psutil
from aiohttp import web

from . import config as C
from . import llm, tools
from .audit import audit, log
from .commands import HELP, route

TZ = ZoneInfo(C.TZ_NAME)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
history: deque = deque(maxlen=12)       # short-term chat context for the LLM
alerts_since_briefing: list[str] = []


# ── helpers ─────────────────────────────────────────────────────────────────

async def owner() -> discord.User:
    return client.get_user(C.OWNER_ID) or await client.fetch_user(C.OWNER_ID)


async def send(dest, text: str, view=None):
    text = text or "(empty)"
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
    msg = None
    for i, chunk in enumerate(chunks):
        msg = await dest.send(chunk, view=view if i == len(chunks) - 1 else None)
    audit("reply", to=str(getattr(dest, "id", dest)), text=text)
    return msg


async def dm(text: str, view=None):
    return await send(await owner(), text, view)


class Confirm(discord.ui.View):
    def __init__(self, timeout=90):
        super().__init__(timeout=timeout)
        self.value = None

    async def interaction_check(self, i: discord.Interaction) -> bool:
        return i.user.id == C.OWNER_ID

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, i: discord.Interaction, _):
        self.value = True
        await i.response.edit_message(view=None)
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, i: discord.Interaction, _):
        self.value = False
        await i.response.edit_message(view=None)
        self.stop()


async def confirm(dest, question: str) -> bool:
    view = Confirm()
    audit("confirm_request", question=question)
    await send(dest, question, view)
    await view.wait()
    audit("confirm_result", question=question, answer=view.value)
    if view.value is None:
        await send(dest, "No answer — cancelled.")
    return bool(view.value)


async def execute_tool(dest, name: str, args: dict) -> str:
    if name in tools.CONFIRM_TOOLS:
        desc = ", ".join(f"{k}={v}" for k, v in args.items())
        if not await confirm(dest, f"Dozer wants to run **{name}** ({desc}). OK?"):
            return "Isaac declined."
    return await tools.call(name, **args)


# ── briefing ────────────────────────────────────────────────────────────────

async def briefing_text() -> str:
    now = datetime.now(TZ)
    states = await tools.service_states()
    down = [u for u, s in states.items() if s != "active"]
    parts = [
        f"☀️ **Morning briefing — {now:%A %d %B}**",
        f"**Weather:** {await tools.weather()}",
        f"**Box:**\n{await tools.get_health()}",
        f"**Services:** {'all up' if not down else 'down: ' + ', '.join(down)}",
        f"**Minecraft:** {await tools.mc_status()}",
        f"**Gaming PC:** {(await tools.pc_status()).replace(chr(10), ' · ')}",
        f"**Alerts since last briefing:** {len(alerts_since_briefing)}"
        + ("".join(f"\n• {a}" for a in alerts_since_briefing[-10:]) if alerts_since_briefing else ""),
    ]
    return "\n".join(parts)


async def briefing_loop():
    hh, mm = map(int, C.BRIEFING_TIME.split(":"))
    last_date = None
    while True:
        now = datetime.now(TZ)
        if now.hour == hh and now.minute == mm and last_date != now.date():
            last_date = now.date()
            try:
                audit("briefing", scheduled=True)
                await dm(await briefing_text())
                alerts_since_briefing.clear()
            except Exception as e:
                audit("error", where="briefing", error=repr(e))
        await asyncio.sleep(20)


# ── watchdog ────────────────────────────────────────────────────────────────

async def alert(text: str):
    alerts_since_briefing.append(f"{datetime.now(TZ):%H:%M} {text}")
    audit("alert", text=text)
    await dm(f"⚠️ {text}")


async def watchdog_loop():
    prev = await tools.service_states()
    disk_alerted = False
    audit("watchdog_start", states=prev)
    while True:
        await asyncio.sleep(60)
        try:
            cur = await tools.service_states()
            for u, s in cur.items():
                p = prev.get(u)
                if p == "active" and s != "active":
                    await alert(f"**{u}** went {s}. Reply `logs {u}` or `restart {u}`.")
                elif p is not None and p != "active" and s == "active":
                    await alert(f"**{u}** is back up.")
            prev = cur
            pct = psutil.disk_usage("/").percent
            if pct >= C.DISK_ALERT_PCT and not disk_alerted:
                disk_alerted = True
                await alert(f"Disk is {pct:.0f}% full.")
            elif pct < C.DISK_ALERT_PCT - 3:
                disk_alerted = False
        except Exception as e:
            audit("error", where="watchdog", error=repr(e))


# ── quote webhook (called by isaac-dev.eu api/send-quote.php) ───────────────

async def quote_hook(request: web.Request):
    if request.headers.get("X-Dozer-Secret") != C.HOOK_SECRET:
        audit("webhook_rejected", path="/hooks/quote", remote=request.remote)
        return web.json_response({"ok": False}, status=403)
    data = await request.json()
    audit("webhook_quote", data=data)
    items = data.get("items", "")
    text = (f"💼 **New IV Studio quote {data.get('ref', '')}**\n"
            f"From: {data.get('who', '?')}\n{items}\n{data.get('totals', '')}")
    await dm(text)
    return web.json_response({"ok": True})


async def start_webhook():
    app = web.Application()
    app.router.add_post("/hooks/quote", quote_hook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", C.HOOK_PORT).start()
    audit("webhook_listening", port=C.HOOK_PORT)


# ── message handling ────────────────────────────────────────────────────────

async def handle(message: discord.Message):
    text = message.content.strip()
    dest = message.channel
    r = route(text)
    audit("route", text=text, route=r.tool if r else "llm")

    if r and r.tool == "help":
        return await send(dest, HELP)
    if r and r.tool == "briefing":
        return await send(dest, await briefing_text())
    if r:
        if r.tool in tools.CONFIRM_TOOLS and not await confirm(dest, r.label or f"Run {r.tool}?"):
            return await send(dest, "Cancelled.")
        return await send(dest, await tools.call(r.tool, **r.args))

    # Anything else -> the brain on the gaming PC
    if not await tools.brain_online():
        if not await confirm(dest, "🧠 The brain (gaming PC) is offline. Wake it and ask? (~30–60 s)"):
            return await send(dest, "OK — fixed commands still work. Type `help`.")
        await send(dest, await tools.call("wake_pc"))
        async with dest.typing():
            for _ in range(36):                      # up to ~3 min
                await asyncio.sleep(5)
                if await tools.brain_online():
                    break
            else:
                audit("error", where="wake_wait", error="brain did not come online")
                return await send(dest, "PC didn't come online in 3 minutes. Is Ollama installed and set to start with Windows?")
    async with dest.typing():
        try:
            answer = await llm.run(list(history), text, lambda n, a: execute_tool(dest, n, a))
        except Exception as e:
            audit("error", where="llm", error=repr(e))
            return await send(dest, f"Brain error: {e.__class__.__name__}. Check `pc`.")
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    await send(dest, answer)


@client.event
async def on_ready():
    audit("startup", user=str(client.user), guilds=[g.name for g in client.guilds])
    if not getattr(client, "_bg", False):
        client._bg = True
        tools.ops.set_notifier(dm)
        asyncio.create_task(watchdog_loop())
        asyncio.create_task(briefing_loop())
        await start_webhook()
        await dm("🟢 Dozer v1 is online. Type `help` for commands.")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return
    if message.author.id != C.OWNER_ID:
        audit("dm_ignored", author=str(message.author), author_id=message.author.id)
        return
    audit("dm_in", text=message.content)
    try:
        await handle(message)
    except Exception as e:
        audit("error", where="handle", error=repr(e))
        log.exception("handle failed")
        await send(message.channel, f"Something broke: {e.__class__.__name__}. It's logged.")


def main():
    if not C.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN missing in .env")
    client.run(C.DISCORD_TOKEN, log_handler=None)
