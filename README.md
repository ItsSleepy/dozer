# Dozer

My self-hosted personal assistant: a Discord DM bot on my home server, with a local LLM on my gaming PC as its "brain". No paid AI APIs; everything runs on hardware I own.

- **Fixed commands first.** Common requests (`status`, `restart nginx`, `remind me in 2h …`, `wake pc`) are matched by a router and run instantly, without the LLM.
- **Local LLM for the rest.** Anything else goes to Ollama (`qwen2.5:14b` on an RTX 4080 Super) with tool calling. If the gaming PC is asleep, Dozer offers to wake it with Wake-on-LAN, waits for the model, and later powers the PC back off if it was the one that woke it. While I'm gaming, it notices and steps aside.
- **Confirm before acting.** Tools are split into READ (run straight away) and ACT (ask first with Yes/No buttons). Destructive operations are blocked outright, and every tool call is written to an audit log.

## What it can do

- **Home server:** health (CPU, RAM, disk, temperatures), service status and restarts, log tails with error summaries, Docker containers, disk usage, apt updates, public IP, website uptime checks and SSL expiry.
- **Minecraft:** status and players, console commands, whitelist, graceful restart, start/stop, world backups on demand and nightly at 04:00 (old ones pruned automatically).
- **Gaming PC:** wake, sleep, shut down, restart or lock; launch Steam games; media and volume; GPU and CPU stats (via a small agent on the PC).
- **Productivity:** reminders and timers, recurring scheduled jobs, notes, long-term memory ("remember that…", "what did I say about…", using SQLite FTS5).
- **Information:** web search through a self-hosted SearXNG with summaries, link summaries (with an SSRF guard), and the weather.
- **Morning briefing at 08:00:** weather, my calendar and inbox, server health, Minecraft, the last backup, today's reminders, and any alerts overnight.
- **Watchdog:** DMs me when a service goes down or comes back, or when the disk is nearly full.
- **Webhooks:** my business website pings Dozer when someone sends a quote request, and Dozer DMs me a summary.
- **Phone app (Android):** push-to-talk and an offline "Hey Dozer" wake word (sherpa-onnx); speech-to-text runs on the server with faster-whisper.

## Layout

- `main.py`: entry point
- `dozer/bot.py`: Discord DMs, confirmations, watchdog, briefing, webhooks (127.0.0.1:8095)
- `dozer/commands.py`: fixed-command router (no LLM)
- `dozer/tools.py`, `dozer/ops.py`, `dozer/pcagent.py`: everything Dozer can do, in READ and ACT tiers
- `dozer/llm.py`: Ollama client and tool-calling loop
- `dozer/memory.py`, `dozer/reminders.py`, `dozer/scheduler.py`: memory, reminders, recurring jobs
- `dozer/voice.py`: speech-to-text and the voice loop for the phone app
- `dozer/audit.py`: logs everything to `logs/audit.jsonl` and `logs/dozer.log`, with secrets scrubbed
- `android/`: the phone app (Kotlin)
- `evals/`: a benchmark of local models on Dozer's tool-calling tasks
- `deploy/`: systemd unit, restart wrapper and sudoers rule, nginx config
- `docs/DEVLOG.md`: the full project history

## Run

Settings come from `.env` (Discord token, owner ID, Ollama URL, gaming PC MAC and IP, and so on; see `dozer/config.py`).

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python main.py
```

For the long-running setup, install `deploy/dozer.service` (see the header of that file).
