"""Minimal async Minecraft RCON client. Independent of the screen console, so it keeps working
after an in-place Java update (the console handler breaks then; RCON doesn't)."""
import asyncio
import struct

from . import config as C


class RconError(Exception):
    pass


async def command(cmd: str, timeout: float = 10.0) -> str:
    pw = C.get("MC_RCON_PASSWORD")
    if not pw:
        raise RconError("RCON password not configured")
    port = int(C.get("MC_RCON_PORT", "25575"))
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), timeout)
    except (OSError, asyncio.TimeoutError) as e:
        raise RconError(f"RCON not reachable ({e.__class__.__name__})")

    async def send(req_id: int, ptype: int, body: str):
        data = struct.pack("<ii", req_id, ptype) + body.encode("utf-8") + b"\x00\x00"
        writer.write(struct.pack("<i", len(data)) + data)
        await writer.drain()

    async def recv():
        (length,) = struct.unpack("<i", await asyncio.wait_for(reader.readexactly(4), timeout))
        payload = await asyncio.wait_for(reader.readexactly(length), timeout)
        req_id, ptype = struct.unpack("<ii", payload[:8])
        return req_id, ptype, payload[8:-2].decode("utf-8", errors="replace")

    try:
        await send(1, 3, pw)                      # login
        rid, _, _ = await recv()
        if rid == -1:
            raise RconError("RCON login rejected")
        await send(2, 2, cmd)                     # command
        _, _, body = await recv()
        return body
    finally:
        writer.close()


async def available() -> bool:
    try:
        await command("list", timeout=3)
        return True
    except Exception:
        return False
