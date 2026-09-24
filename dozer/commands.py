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
`pc` — gaming PC + brain status · `pc info` — idle, games, GPU · `wake pc` — Wake-on-LAN
`pc off|restart|sleep|lock` (asks) · `cancel power` · `launch cs2|steam|discord|medal|roblox`
`play` / `pause` · `next` · `prev` · `mute` · `vol up|down [n]`
`backups` — Minecraft backups · `weather` · `briefing` — morning briefing now
`idea <text>` — add to the ideas tracker
`clips [game] [n]` — recent Medal clips · `post clip [n] [game] [to <channel>]` — posts to BMW (asks)

**Small ops**
`backup` — world backup now (asks) · `prune backups [keep N]` (asks)
`start mc` / `stop mc` (asks) · `whitelist` · `whitelist add|remove <name>` (asks)
`disk [path]` · `top` / `top ram` · `sites` · `updates` · `ip`
`docker` · `docker restart <name>` (asks) · `ls <path>` · `read <file> [lines]`
`help` — this list

**Web**
`search <query>` — web results · `summarise <link> [focus on …]` / `tldr <link>` / just paste a link

**Memory**
`remember that …` · `what did I say about …` · `memories` · `forget <id>` · `forget <words>`

**Reminders**
`remind me in 20m to …` · `remind me at 18:00 to …` · `remind me tomorrow at 9 to …`
`remind me on friday at 17:30 to …` · `remind me every day at 22:00 to …` · `reminders` · `cancel reminder <id>` · `snooze <id> 10m`

**Scheduled tasks**
`schedules` — list · `schedule daily 04:00 <command>` · `schedule weekly sun 04:00 <command>`
`schedule every 6h <command>` (min 15m) · `unschedule <id>` · `pause <id>` · `resume <id>`"""

_P = [
    (r"^(help|commands|\?)$", lambda m: Route("help")),
    (r"^(please )?remind me .+$", lambda m: Route("remind", {"text": m[0]})),
    (r"^(?:search|google|look up|lookup)\s+(.+)$", lambda m: Route("web_search", {"query": m[1]})),
    (r"^(?:summari[sz]e|tldr|tl;dr|sum up)\s+(?:this\s+)?(https?://\S+)(?:\s+(?:focus(?: on)?|about)\s+(.+))?$",
     lambda m: Route("summarise_url", {"url": m[1], "focus": m[2] or ""})),
    (r"^<?(https?://\S+?)>?$", lambda m: Route("summarise_url", {"url": m[1]})),
    (r"^(?:please )?(?:remember|note|save)(?: that| this)?:?\s+(.+)$", lambda m: Route("remember", {"text": m[1]})),
    (r"^(?:what did i (?:say|tell you) about|what do you (?:know|remember) about|recall|search memory for)\s+(.+?)\??$",
     lambda m: Route("recall", {"query": m[1]})),
    (r"^(memories|memory|what do you remember)\??$", lambda m: Route("list_memories")),
    (r"^forget #?(\d+)$", lambda m: Route("forget_memory", {"rid": int(m[1])}, "memory")),
    (r"^forget (?:about |that )?(.+)$", lambda m: Route("forget_search", {"text": m[1]})),
    (r"^(reminders|my reminders|list reminders)$", lambda m: Route("list_reminders")),
    (r"^(cancel|delete|remove) reminder #?(\d+)$", lambda m: Route("cancel_reminder", {"rid": int(m[2])})),
    (r"^snooze #?(\d+)(?: (\d+)\s*(m|min|mins|h|hr|hours?)?)?$", lambda m: Route("snooze_reminder",
        {"rid": int(m[1]), "minutes": int(m[2] or 10) * (60 if (m[3] or "m").startswith("h") else 1)})),
    (r"^(schedules?|scheduled|jobs)$", lambda m: Route("schedules")),
    (r"^schedule (daily \d{1,2}:\d{2}|weekly (?:mon|tue|wed|thu|fri|sat|sun) \d{1,2}:\d{2}|every \d+[hm]) (.+)$",
     lambda m: Route("schedule_add", {"spec": m[1], "command": m[2]})),
    (r"^unschedule #?(\d+)$", lambda m: Route("schedule_remove", {"jid": int(m[1])})),
    (r"^(pause|resume) #?(\d+)$", lambda m: Route("schedule_toggle", {"jid": int(m[2]), "on": m[1].lower() == "resume"})),
    (r"^(status|health|box|how'?s the (box|server))\??$", lambda m: Route("get_health")),
    (r"^services?$", lambda m: Route("get_services")),
    (r"^logs? ([\w@.-]+)(?: (\d+))?$", lambda m: Route("get_logs", {"unit": m[1], "lines": int(m[2] or 20)})),
    (r"^restart (mc|minecraft|the server|eugh)$", lambda m: Route("mc_restart", {}, "Restart Minecraft? (warns players, saves, stops cleanly, starts)")),
    (r"^restart ([\w@.-]+)$", lambda m: Route("restart_service", {"unit": m[1]}, f"Restart **{m[1]}**?")),
    (r"^(mc|minecraft)( status)?$", lambda m: Route("mc_status")),
    (r"^(who'?s on|players|who is on|online)\??$", lambda m: Route("mc_players")),
    (r"^mc (.+)$", lambda m: Route("mc_command", {"command": m[1]}, f"Send `{m[1]}` to the Minecraft console?")),
    (r"^(pc|is (my )?pc on|pc status|brain)\??$", lambda m: Route("pc_status")),
    (r"^wake( up)?( my)?( the)? pc$", lambda m: Route("wake_pc")),
    (r"^pc (info|details)$", lambda m: Route("pc_info")),
    (r"^pc (off|restart|sleep|lock)$", lambda m: Route("pc_power", {"action": m[1].lower()}, f"Gaming PC: **{m[1].lower()}**?")),
    (r"^cancel( the)? (power|power ?off|restart)$", lambda m: Route("pc_cancel_power")),
    (r"^(?:launch|open|start) (cs2|steam|discord|medal|roblox)$", lambda m: Route("pc_launch", {"app": m[1].lower()})),
    (r"^(play|pause|play/pause)$", lambda m: Route("pc_media", {"key": "play_pause"})),
    (r"^(next|skip)$", lambda m: Route("pc_media", {"key": "next"})),
    (r"^(prev|previous|back)$", lambda m: Route("pc_media", {"key": "prev"})),
    (r"^mute$", lambda m: Route("pc_media", {"key": "mute"})),
    (r"^vol(?:ume)? (up|down)(?: (\d+))?$", lambda m: Route("pc_media", {"key": f"vol_{m[1].lower()}", "times": int(m[2] or 5)})),
    (r"^weather$", lambda m: Route("weather")),
    (r"^clips?(?: (.+?))?(?: (\d+))?$", lambda m: Route("medal_clips", {"game": m[1] or "", "n": int(m[2] or 5)})),
    (r"^post (?:my )?clip(?: (\d+))?(?: (?!to )(.+?))?(?: to #?(\S+))?$",
     lambda m: Route("post_clip", {"which": int(m[1] or 1), "game": m[2] or "", "channel": m[3] or ""}, "medal")),
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
