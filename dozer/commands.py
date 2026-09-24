"""Fixed commands: instant, no LLM. Returns a Route or None (-> LLM)."""
import re
from dataclasses import dataclass, field


@dataclass
class Route:
    tool: str
    args: dict = field(default_factory=dict)
    label: str = ""


HELP = """**Dozer v1 — fixed commands** (anything else goes to the brain)
`status` — box health · `services` — service states
`logs <unit> [lines]` — journal tail · `restart <unit>` — asks first
`mc` — Minecraft status · `who's on` — players online
`mc <command>` — console command, asks first
`pc` — gaming PC + brain status · `wake pc` — Wake-on-LAN
`backups` — Minecraft backups · `weather` · `briefing` — morning briefing now
`idea <text>` — add to the ideas tracker
`help` — this list"""

_P = [
    (r"^(help|commands|\?)$", lambda m: Route("help")),
    (r"^(status|health|box|how'?s the (box|server))\??$", lambda m: Route("get_health")),
    (r"^services?$", lambda m: Route("get_services")),
    (r"^logs? ([\w@.-]+)(?: (\d+))?$", lambda m: Route("get_logs", {"unit": m[1], "lines": int(m[2] or 20)})),
    (r"^restart ([\w@.-]+)$", lambda m: Route("restart_service", {"unit": m[1]}, f"Restart **{m[1]}**?")),
    (r"^(mc|minecraft)( status)?$", lambda m: Route("mc_status")),
    (r"^(who'?s on|players|who is on|online)\??$", lambda m: Route("mc_players")),
    (r"^mc (.+)$", lambda m: Route("mc_command", {"command": m[1]}, f"Send `{m[1]}` to the Minecraft console?")),
    (r"^(pc|is (my )?pc on|pc status|brain)\??$", lambda m: Route("pc_status")),
    (r"^wake( up)?( my)?( the)? pc$", lambda m: Route("wake_pc")),
    (r"^weather$", lambda m: Route("weather")),
    (r"^(mc )?backups?$", lambda m: Route("mc_backups")),
    (r"^briefing$", lambda m: Route("briefing")),
    (r"^idea (.+)$", lambda m: Route("add_idea", {"text": m[1]})),
]
PATTERNS = [(re.compile(p, re.I), f) for p, f in _P]


def route(text: str):
    text = text.replace("\u2019", "'")
    t = re.sub(r"^(hey |ok )?dozer[,:]?\s*", "", text.strip(), flags=re.I).strip()
    for rx, build in PATTERNS:
        m = rx.match(t)
        if m:
            return build(m)
    return None
