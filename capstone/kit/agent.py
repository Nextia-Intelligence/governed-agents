"""Kit's agent loop. Ungoverned, like Sam at the end of section 1. Your turn."""

import json
from dataclasses import dataclass, field

from bluekite import shop
from bluekite.model import Model, Turn
from bluekite.trace import Trace

SYSTEM = (
    "You are Kit, the restocking agent of Blue Kite, a small online kite shop. "
    "You order stock, write to suppliers and pay their invoices."
)
MAX_TURNS = 50  # a backstop for the demo, not a control


@dataclass
class KitRun:
    id: str
    ticket: dict
    messages: list = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    reply: str | None = None


def run_request(db, ticket: dict, model: Model, call_tool, out=print) -> KitRun:
    run = KitRun(f"r-{shop.next_id(db, 'run'):04d}", ticket)
    text = f"Request {ticket['id']} from {ticket['from']}:\n{ticket['text']}"
    run.messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": text}]
    trace = Trace(out)
    trace.line(f"request {ticket['id']} · agent kit · run {run.id}")
    while run.steps < MAX_TURNS:
        turn = model.next(run.messages, [])
        run.steps += 1
        run.tokens += turn.tokens
        if turn.call is None:
            run.reply = turn.text
            trace.line(f"kit: {turn.text}")
            break
        result = call_tool(db, run.id, turn.call.tool, turn.call.args)
        trace.step(turn.call, result)
        remember(run, turn, result)
    trace.footer(run.steps, run.tokens)
    return run


def remember(run: KitRun, turn: Turn, result) -> None:
    call_id = f"call-{len(run.messages)}"
    run.messages.append({"role": "assistant", "id": call_id,
                         "call": {"tool": turn.call.tool, "args": turn.call.args}})
    run.messages.append({"role": "tool", "id": call_id, "status": result.status,
                         "content": json.dumps(result.data)})
