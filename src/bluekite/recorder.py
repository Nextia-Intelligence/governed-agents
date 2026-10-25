"""One place for what a run shows: the trace for people, the audit log for records."""

from bluekite.governance import audit, untrusted
from bluekite.governance.approvals import args_hash
from bluekite.model import Call, cost
from bluekite.trace import Trace


class Recorder:
    def __init__(self, db, run, out=print):
        self.db, self.run, self.trace = db, run, Trace(out)

    def log(self, kind: str, **details) -> None:
        audit.record(self.db, self.run, kind, **details)

    def start(self) -> None:
        me = self.run.identity
        self.trace.line(f"ticket {me.ticket_id} · agent {me.agent} · "
                        f"run {me.run_id} · {me.label()}")
        self.log("start", ticket=me.ticket_id, text=f"sender {me.sender}")

    def resume(self) -> None:
        me = self.run.identity
        self.trace.line(f"resume run {me.run_id} · ticket {me.ticket_id} · "
                        f"{me.label()}")
        self.log("resume", ticket=me.ticket_id)

    def flag(self, source: str, found: list[str]) -> None:
        warning = untrusted.warning(source, found)
        self.trace.line(warning)
        self.log("flag", source=source, found=found, text=warning)

    def step(self, call: Call, result) -> None:
        self.trace.step(call, result)
        self.log("call", step=self.run.steps, tool=call.tool, args=call.args,
                 args_hash=args_hash(call), decided=result.decided,
                 status=result.status, summary=result.summary, note=result.note)

    def stop(self, stop) -> None:
        self.trace.line(stop.mark())
        self.log("stop", decided=stop.decided(), text=stop.mark())

    def reply(self, text: str) -> None:
        self.trace.line(f"{self.run.identity.agent}: {text}")
        self.log("reply", text=text)

    def end(self) -> None:
        run = self.run
        extra = "" if run.status == "done" else f" · {run.status}"
        self.trace.footer(run.steps, run.tokens, extra)
        self.log("end", status=run.status, steps=run.steps, tokens=run.tokens,
                 cost=round(cost(run.tokens), 6))
