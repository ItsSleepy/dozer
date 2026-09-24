"""Client for the Windows agent on the gaming PC + auto power-off + gaming detection."""
import asyncio
import time

import aiohttp

from . import config as C
from .audit import audit

IDLE_OFF_AFTER = 30 * 60        # seconds of no input before Dozer powers off a PC it woke
POWER_OFF_DELAY = 120           # grace period (seconds) to cancel
CONFIRM_AGENT = {"pc_power"}

state = {"woke_at": None, "gaming": [], "last_status": None, "last_ok": 0.0}
_notify = None


def set_notifier(fn):
    global _notify
    _notify = fn


async def _req(method: str, path: str, body: dict | None = None, timeout: int = 6) -> dict:
    url = C.get("AGENT_URL", "http://192.168.1.84:8766") + path
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        async with s.request(method, url, json=body, headers={"X-Dozer-Agent": C.get("AGENT_SECRET")}) as r:
            return await r.json()


async def status() -> dict | None:
    try:
        d = await _req("GET", "/status")
        state.update(last_status=d, last_ok=time.time(), gaming=d.get("games", []))
        return d
    except Exception:
        return None


def mark_woken():
    state["woke_at"] = time.time()
    audit("pc_woke_by_dozer")


def keep_alive() -> str:
    """Ollama keep_alive: unload right after answering while a game runs, otherwise 5 min."""
    return "0" if state["gaming"] else "5m"


def _fmt_dur(s: int) -> str:
    h, m = divmod(s // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ── tools ───────────────────────────────────────────────────────────────────

async def pc_info() -> str:
    d = await status()
    if not d:
        return "Gaming PC agent not reachable (PC off, or agent not running)."
    g = d.get("gpu", {})
    gpu = (f"GPU {g['util_pct']}%, {g['vram_used_mb'] / 1024:.1f}/{g['vram_total_mb'] / 1024:.0f} GB VRAM, {g['temp_c']}°C"
           if "util_pct" in g else f"GPU stats unavailable ({g.get('error')})")
    games = ", ".join(d["games"]) if d.get("games") else "none"
    woke = " · woken by Dozer" if state["woke_at"] else ""
    return (f"Up {_fmt_dur(d['uptime_s'])}, idle {_fmt_dur(d['idle_s'])}{woke}\n"
            f"Games running: {games}\n{gpu}")


async def pc_power(action: str, delay: int = 60) -> str:
    action = action.lower().strip()
    if action not in ("off", "restart", "sleep", "lock"):
        return "Action must be off, restart, sleep or lock."
    try:
        d = await _req("POST", "/power", {"action": action, "delay": delay})
    except Exception as e:
        return f"Agent not reachable ({e.__class__.__name__})."
    if action in ("off", "restart", "sleep"):
        state["woke_at"] = None
    return d.get("message") or d.get("error", "?")


async def pc_cancel_power() -> str:
    try:
        d = await _req("POST", "/power", {"action": "cancel"})
        return d.get("message") or d.get("error", "?")
    except Exception as e:
        return f"Agent not reachable ({e.__class__.__name__})."


async def pc_launch(app: str) -> str:
    try:
        d = await _req("POST", "/launch", {"app": app})
        return d.get("message") or d.get("error", "?")
    except Exception as e:
        return f"Agent not reachable ({e.__class__.__name__})."


async def pc_media(key: str, times: int = 1) -> str:
    try:
        d = await _req("POST", "/media", {"key": key, "times": times})
        return d.get("message") or d.get("error", "?")
    except Exception as e:
        return f"Agent not reachable ({e.__class__.__name__})."


AGENT_TOOLS = {"pc_info": pc_info, "pc_power": pc_power, "pc_cancel_power": pc_cancel_power,
               "pc_launch": pc_launch, "pc_media": pc_media}


# ── background loop: gaming detection + auto power-off ─────────────────────

async def loop():
    audit("pcagent_loop_start")
    prev_games: list = []
    while True:
        await asyncio.sleep(60)
        try:
            d = await status()
            if not d:
                state["gaming"] = []
                continue
            games = d.get("games", [])
            if games != prev_games:
                audit("gaming_change", games=games)
                prev_games = games
            woke = state["woke_at"]
            if not woke:
                continue
            # Isaac touched the PC after Dozer woke it -> it's his session now, never auto power-off.
            if d["idle_s"] < 90 and time.time() - woke > 120:
                state["woke_at"] = None
                audit("pc_autooff_disarmed", reason="user activity")
                continue
            if d["idle_s"] >= IDLE_OFF_AFTER and not games and time.time() - woke >= IDLE_OFF_AFTER:
                gpu = d.get("gpu", {}).get("util_pct", 0)
                if gpu > 30:
                    continue            # brain or something else is busy
                res = await pc_power("off", POWER_OFF_DELAY)
                audit("pc_autooff", idle_s=d["idle_s"], result=res)
                if _notify:
                    await _notify(f"💤 Gaming PC idle {_fmt_dur(d['idle_s'])} since I woke it — powering off in "
                                  f"{POWER_OFF_DELAY // 60} min. Reply `cancel power` to stop it.")
        except Exception as e:
            audit("error", where="pcagent_loop", error=repr(e))
