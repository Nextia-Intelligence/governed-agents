"""Watch the controls: counts from the audit log, for a dashboard or an alert."""

from collections import Counter


def summarize(events: list[dict]) -> dict:
    calls = [e for e in events if e["kind"] == "call"]
    stops = [e["decided"] for e in events if e["kind"] == "stop"]
    stops += [e["decided"] for e in calls if e["decided"].get("effect") == "stop"]
    ends = {e["run"]: e for e in events if e["kind"] == "end"}  # the last one counts
    return {
        "runs": Counter(e["status"] for e in ends.values()),
        "calls": len(calls),
        "denials": Counter(e["decided"]["rule"] for e in calls
                           if e["decided"].get("by") == "guard"
                           and e["decided"]["effect"] == "deny"),
        "asked": sum(1 for e in calls if e["decided"].get("effect") == "ask"),
        "decided": Counter(e["decided"]["effect"] for e in calls
                           if e["decided"].get("by") == "approval"),
        "stops": Counter(d["rule"] for d in stops),
        "flags": sum(1 for e in events if e["kind"] == "flag"),
        "tokens": sum(e["tokens"] for e in ends.values()),
    }


def counts(counter: Counter) -> str:
    return ", ".join(f"{key} {value}" for key, value in sorted(counter.items()))
