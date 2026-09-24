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

### Open for Isaac
- [x] Gaming PC: install Ollama, OLLAMA_HOST=0.0.0.0, allow 11434 on LAN, start with Windows, pull 2-3 models to test.
- [x] Install deploy/dozer.service (keeps Dozer running permanently), then stop run-loop.sh.
- [x] Install deploy/dozer-restart + deploy/dozer-sudoers (restart any service). Also fix the stale php8.3-fpm sudoers rule -> php8.5-fpm.
- [ ] Review + apply deploy/send-quote-webhook.md to api/send-quote.php.
- [ ] Medal session -> .env (MEDAL_SESSION) for the clip feature (v1.1).
- [ ] Reset the Dozer token (was pasted in chat) and update .env.
