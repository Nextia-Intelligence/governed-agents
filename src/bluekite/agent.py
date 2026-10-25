"""The agent loop: ask the model, run the tool it picks, repeat until it answers."""

import json

from bluekite import clock, runs, shop, tools
from bluekite.governance import (approvals, budgets, credentials, guard, registry,
                                 untrusted)
from bluekite.governance.identity import Identity, identify
from bluekite.governance.policy import Decision
from bluekite.model import Call, Model
from bluekite.recorder import Recorder
from bluekite.runs import Run
from bluekite.tools import Result

SYSTEM = (
    "You are Sam, the support agent of Blue Kite, a small online kite shop. "
    "Solve the customer's ticket with your tools, then reply to the customer."
)


def first_messages(ticket: dict, identity: Identity) -> list[dict]:
    acting_for = identity.on_behalf_of or "nobody: the sender is not a customer"
    system = (f"{SYSTEM} You act for customer {acting_for}. "
              f"{untrusted.RULE_FOR_THE_MODEL}")
    body = untrusted.wrap(ticket["text"], "ticket")
    text = f"Ticket {ticket['id']} from {ticket['from']}:\n{body}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": text}]


def start_run(db, ticket: dict) -> Run:
    run_id = f"r-{shop.next_id(db, 'run'):04d}"
    identity = identify(db, "sam", run_id, ticket)
    return Run(identity, ticket, messages=first_messages(ticket, identity),
               started=clock.now().isoformat())


def run_ticket(db, ticket: dict, model: Model, out=print) -> Run:
    run = start_run(db, ticket)
    rec = Recorder(db, run, out)
    rec.start()
    flag(rec, run, "ticket", ticket["text"])
    return work(db, run, model, rec)


def resume_run(db, run_id: str, model: Model, out=print) -> Run:
    """Go on with a paused run: first the call that waited, then the loop."""
    run = runs.load(db, run_id)
    if run.status != "paused":
        raise SystemExit(f"run {run_id} is {run.status}, not paused")
    rec = Recorder(db, run, out)
    rec.resume()
    run.started = clock.now().isoformat()  # waiting for a person is not run time
    call = Call(**run.pending)
    result = use_tool(db, run, call)
    rec.step(call, result)
    settle(run, call, result, rec)
    return work(db, run, model, rec)


def work(db, run: Run, model: Model, rec: Recorder) -> Run:
    while run.status == "running":
        stop = budgets.before_turn(db, run)
        if stop:
            run.status = "stopped"
            rec.stop(stop)
            break
        turn = model.next(run.messages, registry.openai_schemas())
        run.steps += 1
        run.tokens += turn.tokens
        budgets.record_spend(db, run, turn.tokens)
        if turn.call is None:
            run.reply, run.status = turn.text, "done"
            rec.reply(turn.text)
            break
        result = use_tool(db, run, turn.call)
        rec.step(turn.call, result)
        settle(run, turn.call, result, rec)
    runs.save(db, run)
    rec.end()
    return run


def settle(run: Run, call: Call, result: Result, rec: Recorder) -> None:
    """What a tool result means for the run: wait, stop, or go on."""
    if result.status == "paused":
        run.status, run.pending = "paused", {"tool": call.tool, "args": call.args}
    elif result.status == "stopped":
        run.status = "stopped"
    else:
        run.status, run.pending = "running", None
        flag(rec, run, f"result of {call.tool}", json.dumps(result.data))
        remember(run, call, result)


def flag(rec: Recorder, run: Run, source: str, text: str) -> None:
    """Warn about text that looks like an instruction. This never blocks."""
    found = untrusted.scan(text)
    if found:
        run.flags.append({"source": source, "found": found})
        rec.flag(source, found)


def use_tool(db, run: Run, call: Call) -> Result:
    """Every tool call goes through here. This is where the controls sit."""
    stop = budgets.before_call(db, run, call)
    if stop:
        return Result("stopped", stop.mark(), {"stopped": stop.reason},
                      decided=stop.decided())
    spec = registry.REGISTRY.get(call.tool)
    problems = registry.validate(spec, call.args) if spec else ["no such tool"]
    if problems:
        return Result("denied", f"✋ schema: {problems[0]}", {"error": problems},
                      decided={"by": "schema", "effect": "deny", "rule": "schema"})
    decision = guard.check(db, run.identity, call)
    decided = {"by": "guard", "effect": decision.effect, "rule": decision.rule}
    if decision.effect == "deny":
        return refused(call, decision)
    note = ""
    if decision.effect == "ask":
        gate = check_approval(db, run, call, decision)
        if gate.status != "approved":
            return gate
        note, decided = gate.summary, gate.decided
    token = credentials.issue(run.identity, spec)
    ctx = tools.ToolContext(db, run.identity, token)
    result = tools.call_tool(ctx, call.tool, call.args)
    result.note, result.decided = note, decided
    return result


def check_approval(db, run: Run, call: Call, decision: Decision) -> Result:
    """Find or ask for the approval of this exact call. "approved" lets it run once."""
    approval = approvals.for_call(db, run.identity.run_id, call)
    if approval is None or approval["status"] == "used":  # single use: ask again
        approval = approvals.request(db, run, call, decision)
    status, aid = approval["status"], approval["id"]
    decided = {"by": "approval", "effect": status, "rule": decision.rule,
               "approval": aid}
    if status == "approved":
        approvals.use(db, aid)
        note = f"✔ approval {aid} · approved by {approval['decided_by']}"
        return Result("approved", note, {}, decided=decided)
    if status == "pending":
        mark = f"⏸ guard: ask {call.tool} · rule {decision.rule} · approval {aid}"
        return Result("paused", mark, {"waiting": aid},
                      decided={**decided, "by": "guard", "effect": "ask"})
    by = f" by {approval['decided_by']}" if status == "rejected" else ""
    mark = f"✋ approval {aid} · {status}{by}"
    return Result("denied", mark, {"denied": f"approval {status}"}, decided=decided)


def refused(call: Call, decision: Decision) -> Result:
    mark = f"✋ guard: {decision.effect} {call.tool} · rule {decision.rule}"
    data = {"denied": decision.rule, "reason": decision.reason}
    decided = {"by": "guard", "effect": "deny", "rule": decision.rule}
    return Result("denied", mark, data, decided=decided)


def remember(run: Run, call: Call, result: Result) -> None:
    """Add the tool call and its result to the conversation the model sees."""
    call_id = f"call-{len(run.messages)}"
    run.messages.append({"role": "assistant", "id": call_id,
                         "call": {"tool": call.tool, "args": call.args}})
    content = untrusted.wrap(json.dumps(result.data), f"tool {call.tool}")
    run.messages.append({"role": "tool", "id": call_id, "status": result.status,
                         "content": content})
