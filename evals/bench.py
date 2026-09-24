"""Model benchmark for Dozer. Usage: venv/bin/python evals/bench.py <model> [<model> ...]
Runs every case against each model through the real agent loop. Tools execute for real,
except confirm-gated ones, which are recorded and auto-declined. Results -> evals/results/."""
import asyncio, json, sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dozer import config as C, llm, tools  # noqa: E402

# expect: tools that must be called (any order); args: required arg values; confirm: must hit a confirm tool;
# no_tools: must not call any tool; say_any: reply must contain one of these (lowercase)
CASES = [
    {"q": "are my websites all up?", "expect": ["site_check"]},
    {"q": "how's the server doing?", "expect": ["get_health"]},
    {"q": "is anyone on minecraft?", "expect": ["mc_players"]},
    {"q": "show me the last 10 log lines of the minecraft server", "expect": ["get_logs"], "args": {"unit": "eugh"}},
    {"q": "is nginx running?", "expect_any": ["get_services"]},
    {"q": "restart the minecraft server", "confirm": ["restart_service", "mc_stop", "mc_start"], "restart_unit": "eugh"},
    {"q": "back up the minecraft world", "confirm": ["mc_backup_now"]},
    {"q": "what backups do I have?", "expect": ["mc_backups"]},
    {"q": "what's using the most RAM?", "expect": ["top_processes"]},
    {"q": "how much disk space is left?", "expect_any": ["disk_usage", "get_health"]},
    {"q": "is my gaming pc on?", "expect": ["pc_status"]},
    {"q": "add an idea: scheduled nightly minecraft backups", "expect": ["add_idea"]},
    {"q": "what's the weather like today?", "expect": ["weather"]},
    {"q": "what's in my Downloads folder on the gaming PC?", "no_tools": True, "say_any": ["don't have", "do not have", "can't", "cannot", "no tool"]},
    {"q": "why did the minecraft server crash last night? find the root cause", "say_any": ["claude"]},
    {"q": "write me a bash script that rotates nginx logs", "say_any": ["claude"]},
    {"q": "hey dozer, how are you?", "no_tools": True},
]


async def run_case(model: str, case: dict) -> dict:
    C.OLLAMA_MODEL = model
    calls, confirms = [], []

    async def ex(name, args):
        calls.append((name, args))
        if name == "add_idea":                      # never touch the real tracker from a benchmark
            return "Added idea #0 (benchmark, not saved)."
        if name in tools.CONFIRM_TOOLS:
            confirms.append(name)
            return "Isaac declined (benchmark)."
        return await tools.call(name, **args)

    t = time.time()
    try:
        reply = await llm.run([], case["q"], ex)
    except Exception as e:
        reply = f"ERROR {e!r}"
    secs = time.time() - t
    names = [n for n, _ in calls]
    fails = []
    if "expect" in case and not all(e in names for e in case["expect"]):
        fails.append(f"expected {case['expect']}")
    if "expect_any" in case and not any(e in names for e in case["expect_any"]):
        fails.append(f"expected one of {case['expect_any']}")
    if "confirm" in case and not any(c in confirms for c in case["confirm"]):
        fails.append(f"no confirm via {case['confirm']}")
    for k, v in case.get("args", {}).items():
        if not any(a.get(k) == v for _, a in calls):
            fails.append(f"{k} != {v}")
    if "restart_unit" in case:
        bad = [a.get("unit") for n, a in calls if n == "restart_service" and a.get("unit") != case["restart_unit"]]
        if bad:
            fails.append(f"restart_service unit {bad} != {case['restart_unit']}")
    if case.get("no_tools") and calls:
        fails.append(f"called tools {names}")
    norm = reply.lower().replace("\u2019", "'")
    if "say_any" in case and not any(s in norm for s in case["say_any"]):
        fails.append(f"reply lacks {case['say_any']}")
    if llm._looks_garbled(reply) or reply.startswith("ERROR") or "couldn't handle that one cleanly" in reply:
        fails.append("garbled/error")
    return {"q": case["q"], "pass": not fails, "fails": fails, "calls": calls, "secs": round(secs, 1), "reply": reply[:300]}


async def main(models):
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    summary = []
    for m in models:
        C.OLLAMA_MODEL = m
        await llm.chat([{"role": "user", "content": "hi"}], tools=False)   # warm-up / load into VRAM
        results = [await run_case(m, c) for c in CASES]
        passed = sum(r["pass"] for r in results)
        avg = sum(r["secs"] for r in results) / len(results)
        summary.append((m, passed, len(results), avg))
        Path(f"evals/results/{stamp}_{m.replace(':', '_').replace('/', '_')}.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False, default=str))
        print(flush=True); print(f"=== {m}: {passed}/{len(results)} passed, avg {avg:.1f}s ===")
        for r in results:
            print(f"{'✅' if r['pass'] else '❌'} {r['secs']:5.1f}s  {r['q'][:55]:55} {'' if r['pass'] else '; '.join(r['fails'])}")
    print("\n=== SUMMARY ===")
    for m, p, n, a in sorted(summary, key=lambda x: (-x[1], x[3])):
        print(f"{m:28} {p:2}/{n}  avg {a:.1f}s")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or [C.OLLAMA_MODEL]))
