"""Dozer v1 — Discord DM interface, confirmations, watchdog, briefing, webhook."""
import asyncio
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
import psutil
from aiohttp import web

from . import config as C
from . import llm, reminders, scheduler, tools
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


# ── reminders ───────────────────────────────────────────────────────────────

class ReminderView(discord.ui.View):
    def __init__(self, rid: int):
        super().__init__(timeout=6 * 3600)
        self.rid = rid

    async def interaction_check(self, i: discord.Interaction) -> bool:
        return i.user.id == C.OWNER_ID

    async def _done(self, i: discord.Interaction, note: str):
        await i.response.edit_message(content=i.message.content + f"\n*{note}*", view=None)
        self.stop()

    @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
    async def done(self, i: discord.Interaction, _):
        audit("reminder_ack", id=self.rid)
        await self._done(i, "✓ done")

    @discord.ui.button(label="Snooze 10m", style=discord.ButtonStyle.secondary)
    async def s10(self, i: discord.Interaction, _):
        await self._done(i, await reminders.snooze(self.rid, 10))

    @discord.ui.button(label="Snooze 1h", style=discord.ButtonStyle.secondary)
    async def s60(self, i: discord.Interaction, _):
        await self._done(i, await reminders.snooze(self.rid, 60))


async def deliver_reminder(r: dict, late: bool):
    due = datetime.fromisoformat(r["due"]) if not r.get("repeat") else None
    tail = " *(late — Dozer was offline)*" if late else ""
    await dm(f"⏰ **Reminder:** {r['text']}{tail}", ReminderView(r["id"]))


# ── scheduled jobs ──────────────────────────────────────────────────────────

async def run_job(job: dict):
    cmd = job["command"]
    r = route(cmd)
    try:
        if r and r.tool == "briefing":
            text = await briefing_text()
        elif r and r.tool in tools.REGISTRY:
            text = await tools.call(r.tool, **r.args)          # confirmed once, at creation
        else:
            async def read_only(name, args):
                if name in tools.CONFIRM_TOOLS:
                    return "Not allowed in a scheduled task (needs confirmation)."
                return await tools.call(name, **args)
            text = await llm.run([], cmd, read_only) if await tools.brain_online() else "Brain offline — skipped."
    except Exception as e:
        text = f"Failed: {e.__class__.__name__}: {e}"
        audit("error", where="run_job", id=job["id"], error=repr(e))
    audit("schedule_result", id=job["id"], result=text)
    await dm(f"⏰ `#{job['id']}` {cmd}\n{text}")


def backup_age_line() -> str:
    files = sorted(tools.ops.BACKUP_DIR.glob("world-*.tar.gz"), key=lambda f: f.stat().st_mtime)
    if not files:
        return "⚠️ no world backups found"
    age = datetime.now().timestamp() - files[-1].stat().st_mtime
    days = age / 86400
    txt = f"{files[-1].name} ({days * 24:.0f} h ago)" if days < 2 else f"⚠️ {files[-1].name} ({days:.0f} days ago)"
    return txt


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
        f"**Last world backup:** {backup_age_line()}",
        *([f"**Today's reminders:**\n" + "\n".join(f"• {l}" for l in reminders.today_lines())] if reminders.today_lines() else []),
        *(["⚠️ **Minecraft is running an outdated Java** — `restart mc` when nobody's on."] if tools.java_stale() else []),
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
    java_alerted = False
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
            stale = tools.java_stale()
            if stale and not java_alerted:
                java_alerted = True
                await alert("Java was updated on disk but Minecraft is still running the old version. "
                            "Its next stop may not save cleanly unless it goes through RCON. "
                            "When nobody's on (`who's on`), run `restart mc`.")
            elif not stale:
                java_alerted = False
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


def _voice_auth(request: web.Request) -> bool:
    ok = request.headers.get("Authorization", "") == f"Bearer {C.get('VOICE_TOKEN')}" and bool(C.get("VOICE_TOKEN"))
    if not ok:
        got = request.headers.get("Authorization", "")
        tok = got[7:] if got.startswith("Bearer ") else got
        audit("voice_rejected", path=request.path, remote=request.headers.get("X-Real-IP", request.remote),
              sent_len=len(tok), expected_len=len(C.get("VOICE_TOKEN")), has_bars="|" in tok, has_space=" " in tok.strip() or tok != tok.strip())
    return ok


async def _voice_reply(transcript: str, reply: str, speak: bool = True) -> web.Response:
    import base64
    from . import voice
    audio = base64.b64encode(await voice.synthesize(reply)).decode() if speak else None
    audit("voice_reply", transcript=transcript, reply=reply)
    return web.json_response({"ok": True, "transcript": transcript, "reply": reply,
                              "speech": voice.speakable(reply), "audio_wav_b64": audio})


async def api_voice(request: web.Request):
    """Phone app: raw audio in (wav/ogg/m4a/webm), transcript + reply text + spoken reply out."""
    if not _voice_auth(request):
        return web.json_response({"ok": False}, status=401)
    from . import voice
    audio = await request.read()
    if not audio or len(audio) > 8_000_000:
        return web.json_response({"ok": False, "error": "no audio or too large"}, status=400)
    t0 = datetime.now()
    text = await voice.transcribe(audio)
    reply = await voice.respond(text) if text else "Sorry, I didn't catch that."
    audit("voice_timing", stt_and_reply_s=round((datetime.now() - t0).total_seconds(), 1), bytes=len(audio))
    return await _voice_reply(text, reply)


async def api_text(request: web.Request):
    if not _voice_auth(request):
        return web.json_response({"ok": False}, status=401)
    from . import voice
    body = await request.json()
    text = (body.get("text") or "").strip()
    reply = await voice.respond(text)
    return await _voice_reply(text, reply, speak=bool(body.get("speak", True)))


async def api_ping(request: web.Request):
    if not _voice_auth(request):
        return web.json_response({"ok": False}, status=401)
    return web.json_response({"ok": True, "brain": await tools.brain_online()})


async def start_webhook():
    app = web.Application(client_max_size=8_500_000)
    app.router.add_post("/hooks/quote", quote_hook)
    app.router.add_post("/api/voice", api_voice)
    app.router.add_post("/api/text", api_text)
    app.router.add_get("/api/ping", api_ping)
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
    if r and r.tool == "remind":
        parts = reminders.split_request(r.args["text"])
        if parts and reminders.parse_when(parts[0]):
            return await send(dest, await tools.call("set_reminder", when=parts[0], text=parts[1]))
        r = None                     # vague time ("after dinner") -> let the brain interpret it
    if r and r.label == "memory":
        r.label = f"Forget memory #{r.args['rid']}?"
    if r and r.label == "discord":
        r.label = await tools.discordmsg.describe(r.args["server"], r.args["channel"], r.args["text"])
    if r and r.tool == "forget_search":
        hits = tools.memory.matches_for_forget(r.args["text"])
        if not hits:
            return await send(dest, f"Nothing in memory matches '{r.args['text']}'.")
        if len(hits) > 1:
            return await send(dest, "Which one? Reply `forget <id>`:\n" + "\n".join(f"`#{h[0]}` {h[1]}" for h in hits))
        if not await confirm(dest, f"Forget `#{hits[0][0]}`: {hits[0][1]}?"):
            return await send(dest, "Kept it.")
        return await send(dest, await tools.call("forget_memory", rid=hits[0][0]))
    if r and r.tool == "schedules":
        return await send(dest, scheduler.describe())
    if r and r.tool == "schedule_add":
        spec, cmd = r.args["spec"], r.args["command"]
        if not scheduler.valid_spec(spec):
            return await send(dest, "Invalid schedule. Use `daily HH:MM`, `weekly sun HH:MM` or `every 6h` / `every 30m` (min 15m).")
        if not await confirm(dest, f"Schedule **{spec}** → `{cmd}`?\nIt will run on its own without asking each time."):
            return await send(dest, "Cancelled.")
        job = scheduler.add(spec, cmd)
        nxt = datetime.fromisoformat(job["next"]).strftime("%a %d %b %H:%M")
        return await send(dest, f"Scheduled `#{job['id']}` — first run {nxt}.")
    if r and r.tool == "schedule_remove":
        return await send(dest, "Removed." if scheduler.remove(r.args["jid"]) else "No such task.")
    if r and r.tool == "schedule_toggle":
        ok = scheduler.set_enabled(r.args["jid"], r.args["on"])
        return await send(dest, ("Resumed." if r.args["on"] else "Paused.") if ok else "No such task.")
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
        scheduler.set_runner(run_job)
        reminders.set_deliver(deliver_reminder)
        asyncio.create_task(reminders.loop())
        tools.pcagent.set_notifier(dm)
        from . import voice
        asyncio.create_task(voice.warm_up())
        asyncio.create_task(tools.pcagent.loop())
        asyncio.create_task(scheduler.loop())
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
