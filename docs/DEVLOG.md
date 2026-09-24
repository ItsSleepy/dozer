# Dozer — Devlog

Self-hosted personal assistant (formerly "Jarvis"). Hub on theminipc, brain on the gaming PC (RTX 4080 Super) via Ollama.
Plan doc: https://claude.ai/code/artifact/789f003e-c1e8-4a4c-9618-52d6a96d7225
Backlog: 🤖 Dozer backlog embed in #ideas (Us bot tracker, ideas #75–#152)

Every entry is dated (UTC). Phases: Planning → Drafting → Confirming → Talking → Prototype.

---

## 2026-09-23 — Planning

- Asked how much work a "personal Jarvis" would be. Estimate: text-only MVP in a weekend, voice +1–2 weeks, solid daily driver ~1–2 months part-time.
- Components identified: LLM brain, tools, wake word, STT, TTS, memory, scheduler.
- Constraint: avoid the Claude API because of cost → local LLM.
- Hardware check: theminipc (Ryzen 5 3500U, ~12 GB usable) too weak for the LLM; gaming PC has RTX 4080 Super (16 GB VRAM) → 14B models comfortably, 20–30B MoE possible.
- Gaming PC is powered off normally (not at the wall) → existing Wake-on-LAN works; no smart relay needed.
- Mini PC = always-on hub; phone/laptop = clients; gaming PC woken on demand; optional auto power-off after idle only if Dozer woke it.
- Security baseline: read = always, act = confirm, destructive = blocked; Cloudflare Access for any public endpoint; LAN-only Ollama.

## 2026-09-23 — Drafting

- Created the plan doc (Overview, Architecture, Capabilities, Access & permissions, Clients, Hardware & cost, Build phases, Risks).
- Clarified activation: phone button/PWA/Discord, laptop hotkey, optional room wake word, scheduler-driven proactive messages.
- Clarified no custom app strictly needed: Discord first, then one PWA for phone + laptop; native only for side-button/hotkey extras.
- Produced a full feature list (75 items) and added it as its own major-project embed in #ideas (tracker code extended with a separate group).

## 2026-09-23 — Confirming

Decisions:
- Orchestrator: custom Python (not Home Assistant).
- LLM when the gaming PC is off: 100% local — wait for boot, no cloud fallback.
- Extra features: IV Studio quote alerts, dissertation log summariser (Ollama-only version), screen/screenshot explain, post a Medal clip by name.
- Laptop: personal only (work laptop out of scope).
- Discord: dedicated bot (not the Us bot — that one is for the couple server). DMs to Isaac for chat and alerts. No quiet hours.
- Restarts allowed (with confirmation): every service, current and future → needs a sudoers rule for a restart-only wrapper.
- Morning briefing: 08:00.
- Quote alerts: webhook fired from api/send-quote.php (submissions already go to Supabase `quotes` + SMTP email).
- Name: "Dozer" (from the "sleepy" handle). Wake word later: custom "Hey Dozer" openWakeWord model.
- Room speaker: not buying until Dozer proves useful after phase 3. Google Nest Mini ruled out (locked mic).

Clip sharing discussion:
- Discord Nitro limit doesn't apply to bot uploads; automating the user account (self-bot / UI automation) rejected — ToS risk.
- MedalBot already in the BMW server; auto-share not wanted (clipping stays manual).
- Medal public API can't see private clips → chosen approach: Medal website API using Isaac's own session (experimental, unofficial; sharing makes a clip viewable by link).

## 2026-09-23 — Talking

- Dozer bot created in the Discord Developer Portal (client ID 1552238430208139337), in BMW Official ✓✓✓ and Tweakers.
- Token stored at /home/sleepy/dozer/.env (0600). To do: reset token later since it was pasted in chat.
- Backlog and doc renamed Jarvis → Dozer.

## 2026-09-23 — Prototype (v1)

### 09:00 UTC — Environment
- Project at /home/sleepy/dozer (git), Python 3.14 venv: discord.py 2.7.1, aiohttp 3.14, psutil 7.2.
- Config in .env (0600): token, owner ID, Ollama URL/model (qwen2.5:14b placeholder), PC IP/MAC, Us-bot API, webhook port/secret, Europe/Malta, Zejtun coords, 08:00 briefing.
- Findings: running PHP is php8.5-fpm but sudoers still allows php8.3-fpm (stale rule). No user linger, no user systemd bus.

### 09:00 UTC — Code
- audit.py: every event -> logs/audit.jsonl + logs/dozer.log; keys containing token/secret/password/session are scrubbed.
- tools.py: READ = health, services, logs, mc_status, mc_players (via screen "list" + log read), pc_status, weather (Open-Meteo, no key);
  ACT = restart_service, mc_command (confirm-gated; stop/op/deop/ban-ip blocked); plus wake_pc (WoL) and add_idea (Us-bot tracker API).
- commands.py: instant fixed commands (help, status, services, logs, restart, mc, who's on, mc <cmd>, pc, wake pc, weather, briefing, idea).
- llm.py: Ollama /api/chat with tool schemas, 5-round agent loop, confirmation enforced for ACT tools.
- bot.py: owner-only DMs (others ignored + logged), Yes/No confirmation buttons (90 s timeout), brain-offline flow (offer WoL, wait up to 3 min),
  12-message short-term context, watchdog every 60 s (service down/up, disk >= 90%), 08:00 Europe/Malta briefing, quote webhook with shared secret.

### 09:01 UTC — Tests
- Router: 14/14 phrases routed correctly (incl. curly apostrophe).
- Live tool reads OK: health (CPU 13%, 73°C, RAM 54%, disk 16%), all 11 services active, nginx logs, MC active + 0/20 online, PC off, weather 27°C.
- Webhook: valid secret -> DM delivered (TEST-0001); wrong secret -> 403 + logged.
- LLM path: NOT yet tested (Ollama not installed on gaming PC).

### 09:02 UTC — Deploy
- Cron supervisor blocked (MCP sandbox: /var/spool/cron and /tmp read-only). Moved lock to logs/.lock.
- Running via deploy/run-loop.sh (restart loop) started from the MCP session. Caveat: stops if eugh-mcp restarts or the box power-cycles
  -> install deploy/dozer.service.
- 09:02:35 Dozer#8769 connected, webhook on 127.0.0.1:8095, watchdog started, "online" DM sent.

### 09:52 UTC — First real use (Isaac, phone, from work)
- Tested help, status, services, mc, who's on, weather, briefing — all routed correctly, no errors in the audit log.
- Not yet exercised: restart (confirm flow), mc <command>, wake pc, idea, the LLM path.

### 11:03 UTC — Confirm flow + tracker (Isaac)
- `restart nginx` -> Yes/No prompt -> confirmed in 3 s -> "Restarted nginx → active". sudo works from Dozer's process.
- `idea test from dozer` -> added as #153 in Quality of life (test entry removed afterwards).
- 11:04 `mc say hello from dozer` -> confirmed -> server log shows "[Server] hello from dozer". Console path verified end to end.
- Still untested: wake pc, LLM path (both need Isaac at home).

### ~16:30 Malta — Brain online (Isaac at home)
- Installed Ollama 0.34.4 on the gaming PC (192.168.1.84; other IPv4s are virtual adapters).
- First launch bound to 127.0.0.1 only — OLLAMA_HOST (User) not picked up by the tray app. Fix: set OLLAMA_HOST=0.0.0.0 at Machine level, kill + relaunch. Now reachable from the mini PC.
- Firewall rule "Ollama (LAN only)" on 11434 for 192.168.1.0/24.
- Pulled qwen2.5:14b (Q4_K_M, 9.0 GB, 32k context).
- Test 1: qwen2.5:14b emitted tool calls as plain JSON text mixed with garbage tokens instead of the tool_calls field (known template quirk). 33.8 s incl. cold load.
- Fix: llm.py fallback parser turns JSON tool calls in the text into real calls (logged as llm_text_tool_calls).
- Test 2 (warm): "How is the server doing and is anyone on Minecraft?" -> get_health + mc_status + mc_players -> correct summary in 4.5 s.
- Next: pull qwen3:14b and compare tool-calling reliability.

### 14:41 UTC — Permanent service
- Isaac installed dozer.service (enabled, active, PID 3930704) and stopped the interim run-loop. Dozer now survives power cycles and eugh-mcp restarts.
- /usr/local/bin/dozer-restart + /etc/sudoers.d/dozer installed; sudo -n works; wrapper rejects bad unit names (exit 2). Any service can now be restarted (with confirmation).
- php8.3-fpm sudoers rule still stale — harmless now, since php8.5-fpm goes through the wrapper.

### 14:42 UTC — First real brain conversations (Isaac)
- Normal questions answered via qwen2.5:14b with tool calls, 1–3 s per turn warm.
- Problem found in the audit log: asked about Minecraft backups, the model guessed — called eugh-mcp "the backup service",
  passed unsupported args to get_services, and looked up non-existent units "backup"/"mc-backup". Root cause: no file/backup tool + no knowledge of the setup.

### 14:45 UTC — Fix: no more guessing
- New tool mc_backups (+ fixed command `backups`): lists /home/sleepy/eugh/backups (4 world backups, 36.7 GB, latest 22 Sep 06:36)
  and /home/sleepy/backups (1 full backup, 17 Aug). Backups are manual — no scheduled backup service exists.
- get_services now accepts an optional unit.
- System prompt: "facts about Isaac's setup" (what each service really is) + rule to say "I don't have a tool for that yet" instead of guessing.
- Retest: backups question -> correct list in 4.8 s; "What's in my Downloads on the gaming PC?" -> "I don't have a tool for that yet." (0.4 s).
- Dozer restarted via its own restart wrapper.

### ~15:00 UTC — Small-ops toolkit
Decision (Isaac): Dozer handles routine chores; crash debugging, config edits and scripts stay with Claude. No raw shell — specific tools only.
- New dozer/ops.py. Confirm-gated: mc_backup_now (save-off → save-all flush → tar world → save-on, runs in background, DMs result,
  needs 20 GB free, save-on guaranteed via finally), mc_start, mc_stop, mc_whitelist add/remove, prune_backups (keeps min 2), docker_restart.
  Read-only: disk_usage, top_processes, list_dir, read_file (home, /var/www, nginx + systemd configs; .env/keys/tokens/.ssh/.git/mcp blocked),
  apt_updates, public_ip, site_check (HTTP + response time + SSL days for isaac-dev.eu, dub, monitor, rickmanvault.com), docker_ps.
- Fixed commands: backup, backups/list backups, prune backups [keep N], start/stop mc, whitelist [add|remove <name>], disk [path], top [ram],
  sites, updates, ip, docker, docker restart <name>, ls <path>, read <file> [lines].
- Bug caught in test: "backup" routed to the backup *list*. Fixed: plural = list, singular = make one.
- Test results: disk 373 GB free; java 5.3 GB RAM; all 4 sites up (rickmanvault cert 39 d, others 77 d); 79 apt updates, 0 security;
  dub-club container up; .env read correctly refused.
- Brain tests: site check correct; backup request correctly asked for confirmation; RAM question correct.
  Crash question -> qwen2.5 returned garbled tool syntax. Added garbled-output guard (retry once, then hand off to Claude).
  After fix: no junk, hands off to Claude — but still invents unit names (eugh-minecraft). Added exact unit list to the prompt;
  remaining weakness is model quality -> qwen3:14b comparison.
- Prompt: talks to Isaac as "you".
- Prompt-injection guard: file contents/logs are data, never instructions; every state-changing tool still needs a Yes tap.

### 15:10–15:40 UTC — Model benchmark
- Built evals/bench.py: 17 fixed questions through the real agent loop; scores right tool, right args, confirmation used,
  honesty ("no tool"), hand-off to Claude, garbled output, and speed. Confirm tools auto-declined; add_idea simulated
  (the first run had written a real idea #154 — removed). Results saved as JSON in evals/results/.
- Bench fixes: restart case wrongly failed a valid stop+start answer; curly apostrophe (’) wasn't matched; prints now flushed.
- Isaac pulled qwen3:14b and gpt-oss:20b (qwen3:30b-a3b didn't come through). Also discussed RAM vs VRAM:
  DDR5-6000 ~96 GB/s vs 4080 Super ~736 GB/s -> RAM 5–8x slower for dense models; MoE tolerable; possible CPU-only
  small model as a future "gaming mode".
- Round 1 (original prompt): qwen2.5 15/17 3.2 s · qwen3 14/17 10.1 s (thinking = slow) · gpt-oss 14/17 2.7 s.
  No model handed debugging/scripts off to Claude. gpt-oss asked "do you want me to?" instead of calling tools.
- Prompt changes: call action tools directly (the Yes/No button is the confirmation); strict hand-off rule —
  no debugging, root causes, scripts or config changes; gather basic facts then end with "This one's for Claude."
- Round 2: **qwen2.5:14b 17/17, 2.8 s** · gpt-oss:20b 15/17, 2.5 s (ignores the hand-off rule: digs through files
  until it hits the tool-loop limit, or gives script advice). 0 garbled / text tool calls in round 2.
- Decision: stay on qwen2.5:14b — perfect score, near-identical speed, 8.4 GB vs 12.8 GB VRAM.
  Briefly switched to gpt-oss, reverted. Dozer restarted on qwen2.5 with the new prompt.
- Side finding: models spotted a Minecraft crash on 23 Sep ~06:17 (systemd exit code 1); server running since.
  Flagged for Claude to investigate.

### 15:38 UTC — Wake-on-LAN test
- Isaac (PC on): "wake the pc up please" -> brain -> wake_pc -> "Wake-on-LAN packet sent." Same wakeonlan/MAC/broadcast as the Us bot's working WoL.
  Full cold-boot flow (brain offline -> offer wake -> wait for Ollama -> answer) still to test with the PC off.
- Bug found in the log: pc_status said "off / unreachable" while Ollama answered — Windows Firewall blocks ping.
  Fix: PC counts as on if ping OR Ollama responds.
- Bug: disk_usage("/") returned "Path not allowed." Fix: always returns free space; folder breakdown only for allowed folders.

### ~16:00 UTC — Investigation: "Minecraft crash" on 23 Sep (Claude)
- Not a crash. 06:15:56 UTC unattended-upgrades ran; 06:17:02 OpenJDK 21 updated in place; 06:17:04 needrestart auto-restarted
  eugh, cs2bot, leetifybot, mc-status-bot, eugh-mcp. eugh's ExecStop (screen "stop") never ran cleanly: the console handler
  died with "Failed to exec spawn helper … after in-place JDK updates", the JVM exited 1 with no "Saving worlds" — unclean stop,
  up to ~5 min of progress lost. Restarted immediately; fine since.
- Will recur on every Java update. Proposed fix: needrestart override for eugh (Isaac, sudo) + Dozer alert when the running
  server uses a replaced Java (not built yet — awaiting go-ahead).
- Noise: "invalid packet ID: 254" on the Sable UDP channel = internet scanners, harmless.

### 16:15 UTC — Quote webhook applied (Isaac approved)
- Appended to /var/www/isaac-dev.eu/api/send-quote.php after the final JSON response, using fastcgi_finish_request()
  so the client never waits on Dozer; 2 s curl timeout; try/catch. Backup: send-quote.php.bak-pre-dozer. php -l clean.
- Test via PHP curl -> {"ok": true} HTTP 200, DM "TEST-PHP" delivered. Site is not a git repo (secret not in version control).

### 16:16 UTC — Scheduled tasks (Dozer's version of Claude's scheduled tasks)
- dozer/scheduler.py: jobs in data/schedules.json; specs `daily HH:MM`, `weekly <day> HH:MM`, `every Nh|Nm` (min 15 m), Europe/Malta.
  Confirm once at creation; runs execute without asking. Fixed commands run directly; free-text jobs go to the brain read-only
  (confirm tools refused). Results DM'd as "⏰ #id command".
- Commands: schedules, schedule …, unschedule <id>, pause <id>, resume <id>.
- Briefing now shows last world backup age (⚠️ if 2+ days).
- Jobs created per Isaac's request: #1 daily 04:00 `backup`, #2 daily 05:00 `prune backups keep 5`. First run 25 Sep 04:00.

### ~16:45 UTC — Medal clips
- Isaac captured the clip-list request in DevTools: GET https://medal.tv/api/content?userId=42525252&... with header
  X-Authentication (user id + mdl_ token). Stored as MEDAL_SESSION / MEDAL_USER_ID in .env (token was visible in a chat
  screenshot — logging out of that Medal browser session will invalidate it; then capture a fresh one).
- Findings: without the privacy param the API returns everything (1,100+ clips, newest 22 Sep 2026). Privacy values:
  0/1 = old public/unlisted, 4 = anyone with the link (1,075 clips, anonymous API GET = 200), 5 = private (anonymous = 403, 25 clips).
  -> No privacy changes needed; Dozer refuses privacy-5 clips. Almost all clips are "Untitled" -> select by game + recency.
  Games: CS2 878, Roblox 67, Minecraft 49, Screen Recording 42, MECCHA CHAMELEON 30, …
- dozer/medal.py: medal_clips(game, n) and post_clip(which, game, channel, note) — posts the Medal share link to a BMW
  channel via the Dozer bot (Discord embeds it; no upload size limits). Default channel #faze_clipz. 2-minute cache,
  newest 300 clips. Expired session -> clear message to refresh MEDAL_SESSION.
- Commands: `clips [game] [n]`, `post clip [n] [game] [to <channel>]` (confirm shows the exact clip + link). Brain tools too.
- Fix: dates now include the year when not this year (13 Mar 2026 vs 09 Apr 2025 looked out of order).

### ~17:10 UTC — Windows agent
- agent/dozer_agent.py (delivered to Isaac as a drop-in file + install_dozer_agent.ps1). Stdlib-only Python, port 8766,
  accepts only theminipc (192.168.1.92 / .100) + shared secret header (AGENT_SECRET in .env). Logs to dozer_agent.log.
  Endpoints: GET /status (uptime, idle via GetLastInputInfo, running games from a process list, nvidia-smi GPU stats),
  POST /power (off/restart with delay + cancel, sleep, lock), /launch (whitelist: cs2, steam, discord, medal, roblox), /media (media keys).
  Installer: finds/installs Python, copies to %LOCALAPPDATA%\DozerAgent, LAN-only firewall rule, logon scheduled task (hidden,
  auto-restart), starts it.
- Dozer side dozer/pcagent.py: tools pc_info, pc_power (confirm), pc_cancel_power, pc_launch, pc_media; commands
  `pc info`, `pc off|restart|sleep|lock`, `cancel power`, `launch <app>`, `play/pause/next/prev/mute`, `vol up|down [n]`.
- Auto power-off: armed only when Dozer's WoL actually woke the PC (brain was offline). Disarmed the moment Isaac uses the PC.
  Fires after 30 min idle, no game running, GPU < 30%: DMs Isaac and powers off with a 2-min grace (`cancel power`).
- Gaming detection: agent polled every 60 s; while a game runs, Ollama keep_alive = 0 (model unloads right after each answer,
  VRAM goes back to the game); otherwise 5 min.

### ~17:25 UTC — Agent installed (Isaac)
- First run from system32 failed (wrong folder); files had downloaded as a zip -> extracted to Downloads\dozer-agent, installer ran.
- Verified from theminipc: `pc info` -> "Up 3h 25m, idle 0m, games none, GPU 16%, 2.7/16 GB VRAM, 52°C".
- Security check: request without the secret -> 403.

### Open for Isaac
- [x] Install the Windows agent (install_dozer_agent.ps1) and run `pc info`.
- [x] Gaming PC: install Ollama, OLLAMA_HOST=0.0.0.0, allow 11434 on LAN, start with Windows, pull 2-3 models to test.
- [x] Install deploy/dozer.service (keeps Dozer running permanently), then stop run-loop.sh.
- [x] Install deploy/dozer-restart + deploy/dozer-sudoers (restart any service). Also fix the stale php8.3-fpm sudoers rule -> php8.5-fpm.
- [ ] Review + apply deploy/send-quote-webhook.md to api/send-quote.php.
- [x] Medal session -> .env (MEDAL_SESSION) for the clip feature.
- [ ] Reset the Dozer token (was pasted in chat) and update .env.
