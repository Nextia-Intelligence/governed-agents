"""The time. Replay mode uses a fixed clock, so every run prints the same output."""

import os
from datetime import datetime, timedelta

FIXED = "2026-10-25T10:00:00"


def now() -> datetime:
    """BLUEKITE_CLOCK holds a fixed time ("--clock"), or "real" for the real time."""
    value = os.environ.get("BLUEKITE_CLOCK", FIXED)
    if value == "real":
        return datetime.now().replace(microsecond=0)
    return datetime.fromisoformat(value)


def later(minutes: int) -> datetime:
    return now() + timedelta(minutes=minutes)
