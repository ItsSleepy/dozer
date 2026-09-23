# Dozer

Isaac's self-hosted personal assistant. v1 = Discord DMs + fixed commands + watchdog + 08:00 briefing + quote webhook,
with an Ollama brain on the gaming PC for anything that isn't a fixed command.

## Layout
- `main.py` — entry point
- `dozer/bot.py` — Discord DMs, confirmations, watchdog, briefing, webhook (127.0.0.1:8095)
- `dozer/commands.py` — fixed-command router (no LLM)
- `dozer/tools.py` — everything Dozer can do (READ vs ACT/confirm tiers)
- `dozer/llm.py` — Ollama client + tool-calling loop
- `dozer/audit.py` — logs everything to `logs/audit.jsonl` + `logs/dozer.log` (secrets scrubbed)
- `docs/DEVLOG.md` — full project history
- `deploy/` — supervisor scripts, systemd unit, restart wrapper + sudoers, quote webhook snippet

## Logs
- `logs/audit.jsonl` — one JSON line per event: dm_in, route, tool_call, tool_result, confirm_request/result,
  llm_request/response, alert, webhook_*, reply, error, startup
- `logs/dozer.log` — same, human-readable
- `logs/stdout.log` — raw process output

## Run
Interim (no sudo): `setsid deploy/run-loop.sh &`
Proper: install `deploy/dozer.service` (see header of that file).
