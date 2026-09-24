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

**Small ops**
`backup` — world backup now (asks) · `prune backups [keep N]` (asks)
`start mc` / `stop mc` (asks) · `whitelist` · `whitelist add|remove <name>` (asks)
`disk [path]` · `top` / `top ram` · `sites` · `updates` · `ip`
`docker` · `docker restart <name>` (asks) · `ls <path>` · `read <file> [lines]`
`help` — this list

**Scheduled tasks**
`schedules` — list · `schedule daily 04:00 <command>` · `schedule weekly sun 04:00 <command>`
`schedule every 6h <command>` (min 15m) · `unschedule <id>` · `pause <id>` · `resume <id>`"""

_P = [
    (r"^(help|commands|\?)$", lambda m: Route("help")),
    (r"^(schedules?|scheduled|jobs)$", lambda m: Route("schedules")),
    (r"^schedule (daily \d{1,2}:\d{2}|weekly (?:mon|tue|wed|thu|fri|sat|sun) \d{1,2}:\d{2}|every \d+[hm]) (.+)$",
     lambda m: Route("schedule_add", {"spec": m[1], "command": m[2]})),
    (r"^unschedule #?(\d+)$", lambda m: Route("schedule_remove", {"jid": int(m[1])})),
    (r"^(pause|resume) #?(\d+)$", lambda m: Route("schedule_toggle", {"jid": int(m[2]), "on": m[1].lower() == "resume"})),
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
    (r"^(mc )?backups$|^list backups$", lambda m: Route("mc_backups")),
    (r"^(make a |do a )?backup( now)?$|^backup (the )?(mc|world|minecraft)$", lambda m: Route("mc_backup_now", {}, "Back up the Minecraft world now? (saving pauses during the archive)")),
    (r"^prune backups?(?: keep (\d+))?$", lambda m: Route("prune_backups", {"keep": int(m[1] or 3)}, f"Delete old world backups, keeping the newest {int(m[1] or 3)}?")),
    (r"^(start|stop) (mc|minecraft)$", lambda m: Route(f"mc_{m[1].lower()}", {}, f"{m[1].capitalize()} the Minecraft server?")),
    (r"^whitelist$", lambda m: Route("mc_whitelist", {"action": "list"})),
    (r"^whitelist (add|remove) (\w{3,16})$", lambda m: Route("mc_whitelist", {"action": m[1].lower(), "player": m[2]}, f"Whitelist {m[1].lower()} **{m[2]}**?")),
    (r"^(disk|du)( usage)?(?: (\S+))?$", lambda m: Route("disk_usage", {"path": m[3] or "/home/sleepy"})),
    (r"^top( ram| cpu)?$", lambda m: Route("top_processes", {"by": (m[1] or " cpu").strip()})),
    (r"^(sites?|site check|websites?)$", lambda m: Route("site_check")),
    (r"^updates?$", lambda m: Route("apt_updates")),
    (r"^(ip|public ip)$", lambda m: Route("public_ip")),
    (r"^(docker|containers)$", lambda m: Route("docker_ps")),
    (r"^docker restart ([\w.-]+)$", lambda m: Route("docker_restart", {"name": m[1]}, f"Restart container **{m[1]}**?")),
    (r"^ls (\S+)$", lambda m: Route("list_dir", {"path": m[1]})),
    (r"^(cat|read) (\S+)(?: (\d+))?$", lambda m: Route("read_file", {"path": m[2], "lines": int(m[3] or 40)})),
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
