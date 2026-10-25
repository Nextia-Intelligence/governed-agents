"""Kit's agent loop, governed with the modules from the course."""

import json

from bluekite import clock, runs, shop
from bluekite.governance import approvals, budgets, registry, untrusted
from bluekite.model import Call, Model
from bluekite.recorder import Recorder
from bluekite.runs import Run
from bluekite.tools import Result
from kit import governance, tools

SYSTEM = (
    "You are Kit, the restocking agent of Blue Kite, a small online kite shop. "
    "You order stock, write to suppliers and pay their invoices. "
    + untrusted.RULE_FOR_THE_MODEL
)


def start(db, ticket: dict) -> Run:
    run_id = f"r-{shop.next_id(db, 'run'):04d}"
    identity = governance.identify(run_id, ticket)
    body = untrusted.wrap(ticket["text"], "request")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Request {ticket['id']} from "
                                            f"{ticket['from']}:\n{body}"}]
    return Run(identity, ticket, messages, started=clock.now().isoformat())


class KitRecorder(Recorder):
    """Sam's recorder. Only the first line says "request", as in the starter."""

    def start(self) -> None:
        me = self.run.identity
        self.trace.line(f"request {me.ticket_id} · agent {me.agent} · "
                        f"run {me.run_id} · {me.label()}")
        self.log("start", ticket=me.ticket_id, text=f"sender {me.sender}")


def run_request(db, ticket: dict, model: Model, out=print) -> Run:
    run = start(db, ticket)
    rec = KitRecorder(db, run, out)
    rec.start()
    if found := untrusted.scan(ticket["text"]):
        rec.flag("request", found)
    while run.status == "running":
        if stop := budgets.before_turn(db, run):
            run.status = "stopped"
            rec.stop(stop)
            break
        turn = model.next(run.messages, [])
        run.steps, run.tokens = run.steps + 1, run.tokens + turn.tokens
        budgets.record_spend(db, run, turn.tokens)
        if turn.call is None:
            run.reply, run.status = turn.text, "done"
            rec.reply(turn.text)
            break
        result = use_tool(db, run, turn.call)
        rec.step(turn.call, result)
        settle(run, turn.call, result)
    runs.save(db, run)
    rec.end()
    return run


def use_tool(db, run: Run, call: Call) -> Result:
    """The same order of checks as Sam: budget, schema, guard, approval, tool."""
    if stop := budgets.before_call(db, run, call):
        return Result("stopped", stop.mark(), {}, decided=stop.decided())
    spec = governance.REGISTRY.get(call.tool)
    problems = registry.validate(spec, call.args) if spec else ["no such tool"]
    if problems:
        return Result("denied", f"✋ schema: {problems[0]}", {"error": problems},
                      decided={"by": "schema", "effect": "deny", "rule": "schema"})
    decision = governance.check(db, run.identity, call)
    decided = {"by": "guard", "effect": decision.effect, "rule": decision.rule}
    mark = f"guard: {decision.effect} {call.tool} · rule {decision.rule}"
    if decision.effect == "deny":
        return Result("denied", f"✋ {mark}", {"denied": decision.reason},
                      decided=decided)
    if decision.effect == "ask":
        approval = approvals.request(db, run, call, decision)
        return Result("paused", f"⏸ {mark} · approval {approval['id']}", {},
                      decided={**decided, "approval": approval["id"]})
    result = tools.call_tool(db, run.identity.run_id, call.tool, call.args)
    result.decided = decided
    return result


def settle(run: Run, call: Call, result: Result) -> None:
    if result.status in ("paused", "stopped"):
        run.status = result.status
        return
    content = untrusted.wrap(json.dumps(result.data), f"tool {call.tool}")
    call_id = f"call-{len(run.messages)}"
    run.messages.append({"role": "assistant", "id": call_id,
                         "call": {"tool": call.tool, "args": call.args}})
    run.messages.append({"role": "tool", "id": call_id, "status": result.status,
                         "content": content})
