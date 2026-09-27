"""Voice mode: speech-to-text (Whisper, mini PC CPU), text-to-speech (Piper), and a hands-free assistant loop
with spoken yes/no confirmations. Used by the /api/voice and /api/text endpoints (phone app)."""
import asyncio
import io
import re
import time
import wave
from collections import deque

from . import config as C
from . import llm, tools
from .audit import audit
from .commands import route

MODELS = C.ROOT / "models"
VOICE = C.get("PIPER_VOICE", "en_GB-alan-medium")
HINT = ("Dozer, Tweakers, BMW, general chat, Warzone, server, Minecraft, nginx, eugh, restart, backup, reminders, remind me, CS2, "
        "gaming PC, wake, Isaac, weather, sites, docker.")
VOICE_RULES = ("You are speaking out loud to Isaac, possibly while he is driving. Reply in 1–3 short spoken sentences. "
               "When he asks you to do something, call the tool straight away — the system asks him yes or no itself, "
               "so never ask for confirmation yourself. "
               "No markdown, no lists, no links, no emojis. Numbers and times in words a person would say.")
YES = re.compile(r"^(yes|yeah|yep|yup|sure|ok(ay)?|do it|go ahead|confirm(ed)?|affirmative|please do)\b", re.I)
NO = re.compile(r"^(no|nope|nah|cancel|stop|don'?t|never ?mind|abort)\b", re.I)

_stt = None
_tts = None
_lock = asyncio.Lock()
history: deque = deque(maxlen=10)
pending: dict | None = None          # {"kind": "tool"|"wake_ask", "tool", "args", "question", "text", "at"}


# ── models ──────────────────────────────────────────────────────────────────

def _load():
    global _stt, _tts
    if _stt is None:
        from faster_whisper import WhisperModel
        _stt = WhisperModel(C.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8",
                            download_root=str(MODELS / "whisper"), cpu_threads=8)
    if _tts is None:
        from piper import PiperVoice
        _tts = PiperVoice.load(str(MODELS / "piper" / f"{VOICE}.onnx"))


async def warm_up():
    t = time.time()
    await asyncio.to_thread(_load)
    audit("voice_models_loaded", seconds=round(time.time() - t, 1), whisper=C.get("WHISPER_MODEL", "base.en"), voice=VOICE)


FIXES = [  # how Isaac's jargon sounds -> what he means
    (r"\b(2|two|to)[- ]?acre\b|\btwi ?cales\b|\btweekers\b|\btweaker'?s\b", "Tweakers"),
    (r"\bwork[- ]?under\b|\bwar zone\b", "Warzone"),
    (r"\bengine ?x\b|\bn ?jinx\b|\bengine ex\b", "nginx"),
    (r"\b(dosa|doza|dozers?|doze her|dose her)\b", "Dozer"),
    (r"\b(p ?h ?p|php) ?(fpm|f p m)\b", "php8.5-fpm"),
    (r"\bc ?s ?2\b|\bcs two\b|\bcounter strike 2\b", "cs2"),
    (r"\b(ugh|eww|yew)\b(?= server| service)", "eugh"),
]


def fix_jargon(text: str) -> str:
    for pat, rep in FIXES:
        text = re.sub(pat, rep, text, flags=re.I)
    return text


async def transcribe(audio: bytes) -> str:
    await asyncio.to_thread(_load)

    def run():
        segs, _ = _stt.transcribe(io.BytesIO(audio), beam_size=1, vad_filter=True, initial_prompt=HINT, language="en")
        return fix_jargon(" ".join(s.text.strip() for s in segs).strip())
    return await asyncio.to_thread(run)


def speakable(text: str) -> str:
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"<?https?://\S+>?", "", t)
    t = re.sub(r"`#?(\d+)`", r"number \1", t)
    t = re.sub(r"[`*_>#|~]", "", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]", "", t)
    t = t.replace("•", "").replace("→", "to").replace("—", ",").replace("°C", " degrees")
    t = re.sub(r"\s*\n\s*", ". ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" .")
    return (t[:600].rsplit(" ", 1)[0] + "…") if len(t) > 600 else t


async def synthesize(text: str) -> bytes:
    await asyncio.to_thread(_load)

    def run():
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            _tts.synthesize_wav(speakable(text) or "Done.", w)
        return buf.getvalue()
    return await asyncio.to_thread(run)


# ── assistant loop ──────────────────────────────────────────────────────────

async def _run_pending(p: dict) -> str:
    if p["kind"] == "wake_ask":
        await tools.call("wake_pc")
        for _ in range(36):
            await asyncio.sleep(5)
            if await tools.brain_online():
                return await _ask_brain(p["text"])
        return "The gaming PC didn't come online in three minutes."
    return await tools.call(p["tool"], **p["args"])


async def _ask_brain(text: str) -> str:
    global pending

    async def execute(name, args):
        global pending
        if name in tools.CONFIRM_TOOLS:
            desc = ", ".join(f"{k} {v}" for k, v in args.items())
            pending = {"kind": "tool", "tool": name, "args": args, "at": time.time(),
                       "question": f"{name.replace('_', ' ')} {desc}".strip()}
            audit("voice_confirm_request", tool=name, args=args)
            return ("NOT DONE YET: this needs Isaac's spoken confirmation. Tell him in one short sentence exactly "
                    "what you are about to do and ask 'yes or no?'.")
        return await tools.call(name, **args)

    answer = await llm.run(list(history), text, execute, extra_system=VOICE_RULES)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    return answer


async def respond(text: str) -> str:
    """One hands-free turn. Returns the reply text (spoken by the caller)."""
    global pending
    async with _lock:
        t = text.strip().rstrip(".!?")
        audit("voice_in", text=t)
        if not t:
            return "Sorry, I didn't catch that."

        if pending and time.time() - pending["at"] < 90:
            p, pending = pending, None
            if YES.match(t):
                audit("voice_confirm_result", answer=True, pending=p)
                return await _run_pending(p)
            if NO.match(t):
                audit("voice_confirm_result", answer=False, pending=p)
                return "Okay, cancelled."
            audit("voice_confirm_result", answer=None, pending=p)       # moved on to something else
        pending = None

        r = route(t)
        if r and r.tool == "help":
            return ("You can ask about the server, Minecraft, your sites, the weather, reminders, or anything else. "
                    "For restarts and other actions I'll ask you to confirm with yes or no.")
        if r and r.tool == "briefing":
            from .bot import briefing_text
            return await briefing_text()
        if r and r.tool == "remind":
            from . import reminders
            parts = reminders.split_request(t)
            if parts and reminders.parse_when(parts[0]):
                return await tools.call("set_reminder", when=parts[0], text=parts[1])
            r = None
        if r and r.tool in ("schedules", "schedule_add", "schedule_remove", "schedule_toggle", "forget_search"):
            return "That one's easier in the chat. I'll leave it for when you're on your phone screen."
        if r and r.label == "discord":
            r.label = await tools.discordmsg.describe(r.args["server"], r.args["channel"], r.args["text"])
        if r and r.tool in tools.CONFIRM_TOOLS:
            q = re.sub(r"[*`>]", "", r.label or f"Run {r.tool}?")
            pending = {"kind": "tool", "tool": r.tool, "args": r.args, "question": q, "at": time.time()}
            return f"{q} Yes or no?"
        if r and r.tool in tools.REGISTRY:
            return await tools.call(r.tool, **r.args)

        if not await tools.brain_online():
            pending = {"kind": "wake_ask", "text": t, "at": time.time()}
            return "My brain on the gaming PC is off. Want me to wake it? That takes about a minute. Yes or no?"
        try:
            return await _ask_brain(t)
        except Exception as e:
            audit("error", where="voice_brain", error=repr(e))
            return "Something went wrong with the brain. Try again in a moment."
