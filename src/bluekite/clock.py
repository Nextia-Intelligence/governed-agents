"""The time. Replay mode uses a fixed clock, so every run prints the same output."""

import os
from datetime import datetime, timedelta

FIXED = "2026-10-25T10:00:00"
_waited = timedelta()  # time that passed on the fixed clock, in this process


def now() -> datetime:
    """BLUEKITE_CLOCK holds a fixed time ("--clock"), or "real" for the real time."""
    value = os.environ.get("BLUEKITE_CLOCK", FIXED)
    if value == "real":
        return datetime.now().replace(microsecond=0)
    return datetime.fromisoformat(value) + _waited


def wait(seconds: int) -> None:
    """Something took time, for example a timeout. The fixed clock moves on too."""
    global _waited
    _waited += timedelta(seconds=seconds)


def later(minutes: int) -> datetime:
    return now() + timedelta(minutes=minutes)


def parse(text: str) -> datetime:
    return datetime.fromisoformat(text)
