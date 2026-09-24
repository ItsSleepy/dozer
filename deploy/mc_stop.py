"""ExecStop for eugh.service: save + stop via RCON (survives in-place Java updates),
falls back to the screen console. Waits for the JVM to exit so systemd doesn't kill it mid-save."""
import asyncio
import subprocess
import sys
import time

sys.path.insert(0, "/home/sleepy/dozer")
import psutil  # noqa: E402
from dozer import rcon  # noqa: E402


def mc_running() -> bool:
    for p in psutil.process_iter(["name", "cwd"]):
        try:
            if p.info["name"] == "java" and p.info["cwd"] == "/home/sleepy/eugh":
                return True
        except psutil.Error:
            pass
    return False


async def main():
    try:
        await rcon.command("save-all flush", timeout=60)
        await rcon.command("stop")
        print("mc_stop: saved + stop sent via RCON")
    except Exception as e:
        print(f"mc_stop: RCON failed ({e}), falling back to screen console")
        subprocess.run(["/usr/bin/screen", "-p", "0", "-S", "eugh", "-X", "stuff", "stop\r"])
    deadline = time.time() + 80
    while time.time() < deadline and mc_running():
        await asyncio.sleep(2)
    print("mc_stop: server exited" if not mc_running() else "mc_stop: still running after 80 s")


asyncio.run(main())
