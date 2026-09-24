"""Everything Dozer can do. Each tool returns plain text.

Tiers:
  READ  - runs immediately
  ACT   - needs Isaac's confirmation (enforced by the caller via CONFIRM_TOOLS)
"""
import asyncio
import re
import shutil
import time
from datetime import timedelta

import aiohttp
import psutil

from . import config as C
from .audit import audit

CONFIRM_TOOLS = {"restart_service", "mc_command"}
UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]{1,64}$")


async def _run(*cmd: str, timeout: int = 30) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "timed out"
    return proc.returncode, out.decode(errors="replace").strip()


# ── READ ────────────────────────────────────────────────────────────────────

async def get_health() -> str:
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    up = timedelta(seconds=int(time.time() - psutil.boot_time()))
    load = ", ".join(f"{x:.2f}" for x in psutil.getloadavg())
    temp = ""
    try:
        temps = psutil.sensors_temperatures()
        for name in ("k10temp", "coretemp", "acpitz"):
            if temps.get(name):
                temp = f"{temps[name][0].current:.0f}°C"
                break
    except Exception:
        pass
    lines = [
        f"CPU {cpu:.0f}% (load {load})" + (f", {temp}" if temp else ""),
        f"RAM {mem.used / 2**30:.1f}/{mem.total / 2**30:.1f} GB ({mem.percent:.0f}%)",
        f"Disk {disk.used / 2**30:.0f}/{disk.total / 2**30:.0f} GB ({disk.percent:.0f}%)",
        f"Uptime {up}",
    ]
    return "\n".join(lines)


async def service_states(units=None) -> dict:
    units = units or C.WATCHED_SERVICES
    out = {}
    for u in units:
        _, s = await _run("systemctl", "is-active", u)
        out[u] = s.splitlines()[0] if s else "unknown"
    return out


async def get_services(unit: str = "") -> str:
    states = await service_states([unit] if unit and UNIT_RE.match(unit) else None)
    return "\n".join(f"{'🟢' if s == 'active' else '🔴'} {u} — {s}" for u, s in states.items())


async def get_logs(unit: str, lines: int = 20) -> str:
    if not UNIT_RE.match(unit):
        return "Invalid unit name."
    lines = max(1, min(int(lines), 60))
    _, out = await _run("journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso")
    return out[-1800:] or "(no log lines)"


async def mc_status() -> str:
    _, active = await _run("systemctl", "is-active", "eugh")
    _, ports = await _run("ss", "-tln")
    listening = ":25565" in ports
    return f"Minecraft (eugh): {active}, {'listening on 25565' if listening else 'NOT listening on 25565'}"


async def mc_players() -> str:
    if not shutil.which("screen"):
        return "screen not available."
    size_before = C.MC_LOG.stat().st_size if C.MC_LOG.exists() else 0
    await _run("screen", "-p", "0", "-S", C.MC_SCREEN, "-X", "stuff", "list\r")
    await asyncio.sleep(1.5)
    if not C.MC_LOG.exists():
        return "Minecraft log not found."
    with C.MC_LOG.open("rb") as f:
        f.seek(size_before)
        new = f.read().decode(errors="replace")
    for line in reversed(new.splitlines()):
        m = re.search(r"There are (\d+) of a max of (\d+) players online:?\s*(.*)", line)
        if m:
            n, mx, names = m.groups()
            return f"{n}/{mx} online" + (f": {names}" if names.strip() else "")
    return "No reply from the server console (is it running?)."


BACKUP_DIRS = {
    "Minecraft world backups": C.MC_LOG.parent.parent / "backups",
    "Full server backups": C.MC_LOG.parent.parent.parent / "backups",
}


async def mc_backups() -> str:
    from datetime import datetime
    out = []
    for label, d in BACKUP_DIRS.items():
        files = sorted((f for f in d.glob("*.tar.gz") if f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True) if d.exists() else []
        total = sum(f.stat().st_size for f in files)
        out.append(f"**{label}** ({d}) — {len(files)} file(s), {total / 2**30:.1f} GB")
        for f in files[:8]:
            st = f.stat()
            out.append(f"• {f.name} — {st.st_size / 2**30:.1f} GB — {datetime.fromtimestamp(st.st_mtime):%d %b %Y %H:%M}")
    out.append("Backups are made manually (no scheduled backup service).")
    return "\n".join(out)


async def pc_status() -> str:
    code, _ = await _run("ping", "-c", "1", "-W", "1", C.PC_IP, timeout=5)
    brain = await brain_online()
    return (f"Gaming PC: {'on' if code == 0 else 'off / unreachable'}\n"
            f"Brain (Ollama): {'online (' + C.OLLAMA_MODEL + ')' if brain else 'offline'}")


async def brain_online() -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"{C.OLLAMA_URL}/api/tags") as r:
                return r.status == 200
    except Exception:
        return False


async def weather() -> str:
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={C.WEATHER_LAT}&longitude={C.WEATHER_LON}"
           "&current=temperature_2m,weather_code,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           f"&timezone={C.TZ_NAME}&forecast_days=1")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(url) as r:
                d = await r.json()
        cur, day = d["current"], d["daily"]
        return (f"{cur['temperature_2m']:.0f}°C now, {day['temperature_2m_min'][0]:.0f}–"
                f"{day['temperature_2m_max'][0]:.0f}°C today, "
                f"{day['precipitation_probability_max'][0]}% chance of rain, "
                f"wind {cur['wind_speed_10m']:.0f} km/h")
    except Exception as e:
        return f"weather unavailable ({e.__class__.__name__})"


# ── ACT (confirmation required) ─────────────────────────────────────────────

async def restart_service(unit: str) -> str:
    if not UNIT_RE.match(unit):
        return "Invalid unit name."
    if unit in C.SUDO_RESTART_OK:
        code, out = await _run("sudo", "-n", "systemctl", "restart", unit, timeout=120)
    elif shutil.which(C.RESTART_WRAPPER):
        code, out = await _run("sudo", "-n", C.RESTART_WRAPPER, unit, timeout=120)
    else:
        return (f"Not allowed to restart {unit} yet — install deploy/dozer-restart "
                "and its sudoers rule (see deploy/README.md).")
    if code != 0:
        return f"Restart failed: {out[-500:]}"
    _, state = await _run("systemctl", "is-active", unit)
    return f"Restarted {unit} → {state}"


async def mc_command(command: str) -> str:
    c = command.strip().lstrip("/")
    if not c:
        return "Empty command."
    if c.split()[0].lower() in ("stop", "op", "deop", "ban-ip"):
        return f"Refused: '{c.split()[0]}' is blocked for Dozer."
    await _run("screen", "-p", "0", "-S", C.MC_SCREEN, "-X", "stuff", f"{c}\r")
    return f"Sent to console: {c}"


async def wake_pc() -> str:
    if not C.PC_MAC:
        return "PC_MAC not configured."
    code, out = await _run("wakeonlan", "-i", C.WOL_BROADCAST, C.PC_MAC)
    return "Wake-on-LAN packet sent." if code == 0 else f"WoL failed: {out}"


async def add_idea(text: str, category: str = "Quality of life") -> str:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(C.US_API_URL, headers={"X-Auth": C.US_API_SECRET},
                              json={"action": "idea_add", "params": {"text": text, "category": category}}) as r:
                d = await r.json()
        return f"Added idea #{d.get('id', '?')} to {category}." if d.get("ok") else f"Tracker error: {d}"
    except Exception as e:
        return f"Tracker unreachable ({e.__class__.__name__})."


# ── registry used by the LLM and the command router ─────────────────────────

REGISTRY = {
    "get_health": get_health,
    "get_services": get_services,
    "get_logs": get_logs,
    "mc_status": mc_status,
    "mc_players": mc_players,
    "pc_status": pc_status,
    "mc_backups": mc_backups,
    "weather": weather,
    "wake_pc": wake_pc,
    "add_idea": add_idea,
    "restart_service": restart_service,
    "mc_command": mc_command,
}


from . import ops  # noqa: E402  (after _run/UNIT_RE are defined)
REGISTRY.update(ops.OPS)
CONFIRM_TOOLS |= ops.CONFIRM_OPS


async def call(name: str, **args) -> str:
    fn = REGISTRY.get(name)
    if not fn:
        return f"Unknown tool {name}."
    audit("tool_call", tool=name, args=args)
    try:
        result = await fn(**args)
    except TypeError as e:
        result = f"Bad arguments for {name}: {e}"
    except Exception as e:
        result = f"{name} failed: {e.__class__.__name__}: {e}"
    audit("tool_result", tool=name, result=result)
    return result
