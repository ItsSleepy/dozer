"""Logs EVERYTHING: every message, command, tool call, result, confirmation,
alert and error goes to logs/audit.jsonl (machine-readable) and
logs/dozer.log (human-readable)."""
import json
import logging
from datetime import datetime, timezone

from .config import LOG_DIR

AUDIT_FILE = LOG_DIR / "audit.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "dozer.log"), logging.StreamHandler()],
)
log = logging.getLogger("dozer")

_SECRET_KEYS = {"token", "secret", "password", "authorization", "session"}


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: ("***" if any(s in k.lower() for s in _SECRET_KEYS) else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def audit(kind: str, **fields):
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, **_scrub(fields)}
    with AUDIT_FILE.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    short = {k: (str(v)[:200]) for k, v in fields.items()}
    log.info("%s %s", kind, short)
