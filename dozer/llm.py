"""Ollama client with tool calling. The model runs on the gaming PC."""
import json
import re

import aiohttp

from . import config as C
from .audit import audit

SYSTEM_PROMPT = """You are Dozer, Isaac's self-hosted personal assistant.
You run on his home server (theminipc) and talk to him over Discord DMs.
Be concise and direct. Use tools to check real state instead of guessing.
Temperatures in Celsius. If a tool needs confirmation, the system will ask Isaac;
just call it. Never invent tool results."""


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOL_SCHEMAS = [
    _fn("get_health", "CPU, RAM, disk, temperature and uptime of the home server."),
    _fn("get_services", "Status of all watched services on the home server."),
    _fn("get_logs", "Recent journal log lines for a systemd unit.",
        {"unit": {"type": "string"}, "lines": {"type": "integer"}}, ["unit"]),
    _fn("mc_status", "Whether the Minecraft server (eugh) is running."),
    _fn("mc_players", "Who is online on the Minecraft server."),
    _fn("pc_status", "Whether the gaming PC and the Ollama brain are online."),
    _fn("weather", "Current weather and today's forecast for Isaac's area."),
    _fn("wake_pc", "Send Wake-on-LAN to the gaming PC."),
    _fn("add_idea", "Add an idea to Isaac's Discord ideas tracker.",
        {"text": {"type": "string"}, "category": {"type": "string"}}, ["text"]),
    _fn("restart_service", "Restart a systemd service (asks Isaac first).",
        {"unit": {"type": "string"}}, ["unit"]),
    _fn("mc_command", "Send a command to the Minecraft console (asks Isaac first).",
        {"command": {"type": "string"}}, ["command"]),
]


async def chat(messages: list, tools: bool = True) -> dict:
    payload = {"model": C.OLLAMA_MODEL, "messages": messages, "stream": False,
               "options": {"temperature": 0.3}}
    if tools:
        payload["tools"] = TOOL_SCHEMAS
    audit("llm_request", model=C.OLLAMA_MODEL, last=messages[-1].get("content", "")[:500])
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as s:
        async with s.post(f"{C.OLLAMA_URL}/api/chat", json=payload) as r:
            r.raise_for_status()
            data = await r.json()
    msg = data.get("message", {})
    audit("llm_response", content=msg.get("content", "")[:1000],
          tool_calls=[tc.get("function", {}).get("name") for tc in msg.get("tool_calls", []) or []],
          eval_count=data.get("eval_count"), total_ms=int(data.get("total_duration", 0) / 1e6))
    return msg


_TEXT_CALL = re.compile(r'\{\s*"name"\s*:\s*"([a-z_]+)"\s*,\s*"arguments"\s*:\s*(\{[^{}]*\})\s*\}')
_KNOWN = {t["function"]["name"] for t in TOOL_SCHEMAS}


def _text_tool_calls(content: str) -> list:
    """Fallback: some models write tool calls as JSON text instead of using the API field."""
    calls = []
    for name, args in _TEXT_CALL.findall(content or ""):
        if name in _KNOWN:
            try:
                calls.append({"function": {"name": name, "arguments": json.loads(args)}})
            except json.JSONDecodeError:
                pass
    if calls:
        audit("llm_text_tool_calls", count=len(calls), names=[c["function"]["name"] for c in calls])
    return calls


async def run(history: list, user_text: str, execute_tool) -> str:
    """Agent loop: model -> tools -> model, max 5 rounds.
    execute_tool(name, args) handles confirmation and returns a result string."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": user_text}]
    for _ in range(5):
        msg = await chat(messages)
        calls = msg.get("tool_calls") or _text_tool_calls(msg.get("content", ""))
        if calls and not msg.get("tool_calls"):
            msg = {"role": "assistant", "content": "", "tool_calls": calls}
        if not calls:
            return msg.get("content", "").strip() or "(no reply)"
        messages.append(msg)
        for tc in calls:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = await execute_tool(fn.get("name", ""), args)
            messages.append({"role": "tool", "content": result})
    return "I got stuck in a tool loop — try rephrasing."
