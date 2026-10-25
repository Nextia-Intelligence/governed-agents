"""The agent loop: ask the model, run the tool it picks, repeat until it answers."""

import json
from dataclasses import dataclass, field

from bluekite import shop, tools
from bluekite.model import Model, Turn
from bluekite.trace import Trace

SYSTEM = (
    "You are Sam, the support agent of Blue Kite, a small online kite shop. "
    "Solve the customer's ticket with your tools, then reply to the customer."
)
MAX_TURNS = 50  # a backstop so a demo cannot run forever; real limits come later


@dataclass
class Run:
    id: str
    ticket: dict
    agent: str = "sam"
    messages: list = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    reply: str | None = None


def first_messages(ticket: dict) -> list[dict]:
    text = f"Ticket {ticket['id']} from {ticket['from']}:\n{ticket['text']}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]


def start_run(db, ticket: dict) -> Run:
    run_id = f"r-{shop.next_id(db, 'run'):04d}"
    return Run(run_id, ticket, messages=first_messages(ticket))


def run_ticket(db, ticket: dict, model: Model, out=print) -> Run:
    run = start_run(db, ticket)
    trace = Trace(out)
    trace.line(f"ticket {ticket['id']} · agent {run.agent} · run {run.id}")
    while run.steps < MAX_TURNS:
        turn = model.next(run.messages, tools.SCHEMAS)
        run.steps += 1
        run.tokens += turn.tokens
        if turn.call is None:
            run.reply = turn.text
            trace.line(f"{run.agent}: {turn.text}")
            break
        result = tools.call_tool(tools.ToolContext(db, run.id), turn.call.tool,
                                 turn.call.args)
        trace.step(turn.call, result.summary)
        remember(run, turn, result)
    trace.footer(run.steps, run.tokens)
    return run


def remember(run: Run, turn: Turn, result: tools.Result) -> None:
    """Add the tool call and its result to the conversation the model sees."""
    call_id = f"call-{run.steps}"
    run.messages.append({"role": "assistant", "id": call_id,
                         "call": {"tool": turn.call.tool, "args": turn.call.args}})
    run.messages.append({"role": "tool", "id": call_id, "status": result.status,
                         "content": json.dumps(result.data)})
