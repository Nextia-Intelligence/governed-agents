"""The agent loop: ask the model, run the tool it picks, repeat until it answers."""

import json

from bluekite import clock, runs, shop, tools
from bluekite.governance import (approvals, budgets, credentials, guard, registry,
                                 untrusted)
from bluekite.governance.identity import Identity, identify
from bluekite.governance.policy import Decision
from bluekite.model import Call, Model
from bluekite.runs import Run
from bluekite.tools import Result
from bluekite.trace import Trace

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
    me = run.identity
    trace = Trace(out)
    trace.line(f"ticket {ticket['id']} · agent {me.agent} · run {me.run_id} · "
               f"{me.label()}")
    flag(trace, run, "ticket", ticket["text"])
    return work(db, run, model, trace)


def resume_run(db, run_id: str, model: Model, out=print) -> Run:
    """Go on with a paused run: first the call that waited, then the loop."""
    run = runs.load(db, run_id)
    if run.status != "paused":
        raise SystemExit(f"run {run_id} is {run.status}, not paused")
    trace = Trace(out)
    trace.line(f"resume run {run_id} · ticket {run.ticket['id']} · "
               f"{run.identity.label()}")
    run.started = clock.now().isoformat()  # waiting for a person is not run time
    call = Call(**run.pending)
    result = use_tool(db, run, call)
    trace.step(call, result)
    settle(run, call, result, trace)
    return work(db, run, model, trace)


def work(db, run: Run, model: Model, trace: Trace) -> Run:
    while run.status == "running":
        stop = budgets.before_turn(db, run)
        if stop:
            run.status = "stopped"
            trace.line(stop.mark())
            break
        turn = model.next(run.messages, registry.openai_schemas())
        run.steps += 1
        run.tokens += turn.tokens
        budgets.record_spend(db, run, turn.tokens)
        if turn.call is None:
            run.reply, run.status = turn.text, "done"
            trace.line(f"{run.identity.agent}: {turn.text}")
            break
        result = use_tool(db, run, turn.call)
        trace.step(turn.call, result)
        settle(run, turn.call, result, trace)
    runs.save(db, run)
    extra = "" if run.status == "done" else f" · {run.status}"
    trace.footer(run.steps, run.tokens, extra)
    return run


def settle(run: Run, call: Call, result: Result, trace: Trace) -> None:
    """What a tool result means for the run: wait, stop, or go on."""
    if result.status == "paused":
        run.status, run.pending = "paused", {"tool": call.tool, "args": call.args}
    elif result.status == "stopped":
        run.status = "stopped"
    else:
        run.status, run.pending = "running", None
        flag(trace, run, f"result of {call.tool}", json.dumps(result.data))
        remember(run, call, result)


def flag(trace: Trace, run: Run, source: str, text: str) -> None:
    """Warn about text that looks like an instruction. This never blocks."""
    found = untrusted.scan(text)
    if found:
        run.flags.append({"source": source, "found": found})
        trace.line(untrusted.warning(source, found))


def use_tool(db, run: Run, call: Call) -> Result:
    """Every tool call goes through here. This is where the controls sit."""
    stop = budgets.before_call(db, run, call)
    if stop:
        return Result("stopped", stop.mark(), {"stopped": stop.reason})
    spec = registry.REGISTRY.get(call.tool)
    if spec is None:
        return Result("denied", f"✋ registry: no tool {call.tool}",
                      {"error": "no tool"})
    problems = registry.validate(spec, call.args)
    if problems:
        return Result("denied", f"✋ schema: {problems[0]}", {"error": problems})
    decision = guard.check(db, run.identity, call)
    note = ""
    if decision.effect == "deny":
        return refused(call, decision)
    if decision.effect == "ask":
        blocked, note = check_approval(db, run, call, decision)
        if blocked:
            return blocked
    token = credentials.issue(run.identity, spec)
    ctx = tools.ToolContext(db, run.identity, token)
    result = tools.call_tool(ctx, call.tool, call.args)
    result.note = note
    return result


def check_approval(db, run: Run, call: Call, decision: Decision):
    """Returns (a result that stops the call, or None) and a note for the trace."""
    approval = approvals.for_call(db, run.identity.run_id, call)
    if approval is None or approval["status"] == "used":  # single use: ask again
        approval = approvals.request(db, run, call, decision)
    status, aid = approval["status"], approval["id"]
    if status == "approved":
        approvals.use(db, aid)
        return None, f"✔ approval {aid} · approved by {approval['decided_by']}"
    if status == "pending":
        mark = f"⏸ guard: ask {call.tool} · rule {decision.rule} · approval {aid}"
        return Result("paused", mark, {"waiting": aid}), ""
    by = f" by {approval['decided_by']}" if status == "rejected" else ""
    mark = f"✋ approval {aid} · {status}{by}"
    return Result("denied", mark, {"denied": f"approval {status}"}), ""


def refused(call: Call, decision: Decision) -> Result:
    mark = f"✋ guard: {decision.effect} {call.tool} · rule {decision.rule}"
    data = {"denied": decision.rule, "reason": decision.reason}
    return Result("denied", mark, data)


def remember(run: Run, call: Call, result: Result) -> None:
    """Add the tool call and its result to the conversation the model sees."""
    call_id = f"call-{len(run.messages)}"
    run.messages.append({"role": "assistant", "id": call_id,
                         "call": {"tool": call.tool, "args": call.args}})
    content = untrusted.wrap(json.dumps(result.data), f"tool {call.tool}")
    run.messages.append({"role": "tool", "id": call_id, "status": result.status,
                         "content": content})
