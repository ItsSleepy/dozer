"""Loads /home/sleepy/dozer/.env into a simple settings object."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


_env = {**_load_env(ROOT / ".env"), **{k: v for k, v in os.environ.items() if k.startswith("DOZER_")}}


def get(key: str, default: str = "") -> str:
    return _env.get(key, default)


DISCORD_TOKEN = get("DISCORD_TOKEN")
OWNER_ID = int(get("OWNER_ID", "0"))
OLLAMA_URL = get("OLLAMA_URL", "http://192.168.1.84:11434").rstrip("/")
OLLAMA_MODEL = get("OLLAMA_MODEL", "qwen2.5:14b")
PC_IP = get("PC_IP", "192.168.1.84")
PC_MAC = get("PC_MAC")
WOL_BROADCAST = get("WOL_BROADCAST", "255.255.255.255")
US_API_URL = get("US_API_URL", "http://127.0.0.1:8081/api/action")
US_API_SECRET = get("US_API_SECRET")
HOOK_PORT = int(get("HOOK_PORT", "8095"))
# Phone-app API (/api/voice, /api/text, /api/ping). Off = Discord DMs are the only interface.
# Set MOBILE_API=1 in .env to bring it back.
MOBILE_API = get("MOBILE_API", "0") == "1"
# DNS-only hostnames that point straight at the home IP; watched for IP drift.
DDNS_WATCHED_HOSTS = ["mc.isaac-dev.eu", "mcp.isaac-dev.eu", "origin.isaac-dev.eu"]
# Websites loaded every 2 minutes. Down = no answer, timeout, HTTP 5xx/522, or a 4xx other than 401/403.
WATCHED_SITES = {
    "IV Studio": "https://iv-studio.net/",
    "Rickman Vault": "https://rickmanvault.com/",
    "Portfolio (isaac-dev.eu)": "https://isaac-dev.eu/",
    "Dub": "https://dub.isaac-dev.eu/",
}
HOOK_SECRET = get("HOOK_SECRET")
TZ_NAME = get("TZ_NAME", "Europe/Malta")
WEATHER_LAT = float(get("WEATHER_LAT", "35.856"))
WEATHER_LON = float(get("WEATHER_LON", "14.533"))
BRIEFING_TIME = get("BRIEFING_TIME", "08:00")

# Services Dozer watches and reports on.
WATCHED_SERVICES = [
    "mc-vanilla", "mc-party", "nginx", "php8.5-fpm", "netdata", "docker",
    "discord-bot", "fun-bot", "cs2bot", "leetifybot", "mc-status-bot", "eugh-mcp", "portfolio",
]
# Restartable today via the existing sudoers allowlist.
SUDO_RESTART_OK = {"eugh", "nginx", "php8.3-fpm"}
# Wrapper script (installed by Isaac) that allows restarting any unit.
RESTART_WRAPPER = "/usr/local/bin/dozer-restart"

DISK_ALERT_PCT = 90
MC_LOG = Path("/home/sleepy/eugh/logs/latest.log")
MC_SCREEN = "eugh"
