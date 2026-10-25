"""Replay a run from its audit events: the same trace, without the model or the shop."""

from bluekite.model import Call
from bluekite.tools import Result
from bluekite.trace import Trace


def replay(events: list[dict], out=print) -> None:
    trace = Trace(out)
    for e in events:
        if e["kind"] == "start":
            trace.line(f"ticket {e['ticket']} · agent {e['agent']} · run {e['run']} · "
                       f"for {e['for'] or 'unknown sender'}")
        elif e["kind"] == "resume":
            trace.line(f"resume run {e['run']} · ticket {e['ticket']} · "
                       f"for {e['for']}")
        elif e["kind"] in ("flag", "stop"):
            trace.line(e["text"])
        elif e["kind"] == "call":
            result = Result(e["status"], e["summary"], {}, e.get("note", ""))
            trace.step(Call(e["tool"], e["args"]), result)
        elif e["kind"] == "reply":
            trace.line(f"{e['agent']}: {e['text']}")
        elif e["kind"] == "end":
            extra = "" if e["status"] == "done" else f" · {e['status']}"
            trace.footer(e["steps"], e["tokens"], extra)
