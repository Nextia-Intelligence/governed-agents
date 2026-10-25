"""The audit trail: one JSON event per step in state/audit.jsonl, hash-chained.

Each event holds the hash of the event before it. Change, add or delete one
line, and the hashes no longer fit: `bluekite audit verify` sees it.
"""

import hashlib
import json
import re

from bluekite import clock, shop

START = "0" * 64  # the "previous hash" of the first event
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(\+\d{1,3}[ -]?)?(\(\d{3}\)|\d{3})[ -]?\d{3}[ -]\d{4}")
PERSONAL_ARGS = ("address",)  # arguments that are personal data
TEXT_FIELDS = ("summary", "text", "note")  # free text that may hold personal data


def log_path():
    return shop.state_dir() / "audit.jsonl"


def read_events() -> list[dict]:
    path = log_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def digest(value) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def record(db, run, kind: str, **details) -> dict:
    """Add one event to the end of the chain. Personal data is removed first."""
    events = read_events()
    event = {"seq": len(events) + 1, "at": clock.now().isoformat(), "kind": kind,
             "run": run.identity.run_id, "agent": run.identity.agent,
             "for": run.identity.on_behalf_of, **redact(db, details),
             "prev": events[-1]["hash"] if events else START}
    event["hash"] = digest(event)
    with log_path().open("a") as log:
        log.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def redact(db, details: dict) -> dict:
    """Ids stay (C-102 is enough to find the customer); names, emails, addresses go."""
    clean = dict(details)
    if "args" in clean:
        clean["args"] = {key: "[redacted]" if key in PERSONAL_ARGS else value
                         for key, value in clean["args"].items()}
    for key in TEXT_FIELDS:
        if isinstance(clean.get(key), str):
            clean[key] = redact_text(db, clean[key])
    return clean


def redact_text(db, text: str) -> str:
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    for row in db.execute("select name, address from customers"):
        text = text.replace(row["name"], "[name]").replace(row["address"], "[address]")
    return text


def verify() -> tuple[bool, str]:
    """Check every hash and every link. Returns (ok, message)."""
    events, prev = read_events(), START
    for n, event in enumerate(events, start=1):
        body = {key: value for key, value in event.items() if key != "hash"}
        if event.get("seq") != n or event.get("prev") != prev:
            return False, f"broken at event #{n}: the chain is cut"
        if digest(body) != event["hash"]:
            return False, f"broken at event #{n}: the hash does not match"
        prev = event["hash"]
    return True, f"ok · {len(events)} events · chain intact"


def for_run(run_id: str) -> list[dict]:
    return [event for event in read_events() if event["run"] == run_id]
