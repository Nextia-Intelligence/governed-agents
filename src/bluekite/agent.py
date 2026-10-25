"""The agent loop: ask the model, run the tool it picks, repeat until it answers."""

import json
from dataclasses import dataclass, field

from bluekite import shop, tools
from bluekite.governance import credentials, guard, registry
from bluekite.governance.identity import Identity, identify
from bluekite.model import Call, Model, Turn
from bluekite.tools import Result
from bluekite.trace import Trace

SYSTEM = (
    "You are Sam, the support agent of Blue Kite, a small online kite shop. "
    "Solve the customer's ticket with your tools, then reply to the customer."
)
MAX_TURNS = 50  # a backstop so a demo cannot run forever; real limits come later


@dataclass
class Run:
    identity: Identity
    ticket: dict
    messages: list = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    reply: str | None = None


def first_messages(ticket: dict, identity: Identity) -> list[dict]:
    acting_for = identity.on_behalf_of or "nobody: the sender is not a customer"
    system = f"{SYSTEM} You act for customer {acting_for}."
    text = f"Ticket {ticket['id']} from {ticket['from']}:\n{ticket['text']}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": text}]


def start_run(db, ticket: dict) -> Run:
    run_id = f"r-{shop.next_id(db, 'run'):04d}"
    identity = identify(db, "sam", run_id, ticket)
    return Run(identity, ticket, messages=first_messages(ticket, identity))


def run_ticket(db, ticket: dict, model: Model, out=print) -> Run:
    run = start_run(db, ticket)
    me = run.identity
    trace = Trace(out)
    trace.line(f"ticket {ticket['id']} · agent {me.agent} · run {me.run_id} · "
               f"{me.label()}")
    while run.steps < MAX_TURNS:
        turn = model.next(run.messages, registry.openai_schemas())
        run.steps += 1
        run.tokens += turn.tokens
        if turn.call is None:
            run.reply = turn.text
            trace.line(f"{me.agent}: {turn.text}")
            break
        result = use_tool(db, run, turn.call)
        trace.step(turn.call, result)
        remember(run, turn, result)
    trace.footer(run.steps, run.tokens)
    return run


def use_tool(db, run: Run, call: Call) -> Result:
    """Every tool call goes through here. This is where the controls sit."""
    spec = registry.REGISTRY.get(call.tool)
    if spec is None:
        return Result("denied", f"✋ registry: no tool {call.tool}", 
                      {"error": "no tool"})
    problems = registry.validate(spec, call.args)
    if problems:
        return Result("denied", f"✋ schema: {problems[0]}", {"error": problems})
    decision = guard.check(db, run.identity, call)
    if decision.effect != "allow":
        return refused(call, decision)
    token = credentials.issue(run.identity, spec)
    ctx = tools.ToolContext(db, run.identity, token)
    return tools.call_tool(ctx, call.tool, call.args)


def refused(call: Call, decision) -> Result:
    mark = f"✋ guard: {decision.effect} {call.tool} · rule {decision.rule}"
    if decision.effect == "ask":
        mark += " · denied for now"
    data = {"denied": decision.rule, "reason": decision.reason}
    return Result("denied", mark, data)


def remember(run: Run, turn: Turn, result: Result) -> None:
    """Add the tool call and its result to the conversation the model sees."""
    call_id = f"call-{run.steps}"
    run.messages.append({"role": "assistant", "id": call_id,
                         "call": {"tool": turn.call.tool, "args": turn.call.args}})
    run.messages.append({"role": "tool", "id": call_id, "status": result.status,
                         "content": json.dumps(result.data)})
