"""The `bluekite` command."""

import argparse
import json

from bluekite import shop
from bluekite.agent import run_ticket
from bluekite.governance import cedar_policy, guard
from bluekite.governance.identity import Identity
from bluekite.governance.registry import REGISTRY
from bluekite.model import Call
from bluekite.trace import show_call
from bluekite.model import LiveModel, ReplayModel
from bluekite.tickets import get_ticket, load_tickets


def make_model(ticket_id: str, live: bool):
    return LiveModel() if live else ReplayModel(ticket_id)


def cmd_reset(args) -> None:
    shop.reset()
    print("reset: 3 customers, 4 orders, no refunds, no changes")


def cmd_tickets(args) -> None:
    tickets = load_tickets()
    width = max(len(ticket_id) for ticket_id in tickets) + 2  # ids never touch emails
    for ticket in tickets.values():
        text = ticket["text"].splitlines()[0]
        text = text if len(text) <= 46 else text[:45] + "…"  # short enough for a video
        print(f"{ticket['id']:<{width}}{ticket['from']:<26}{text}")


def cmd_run(args) -> None:
    ids = list(load_tickets()) if args.all else args.tickets
    if not ids:
        raise SystemExit("give a ticket id, or --all")
    db = shop.connect()
    for n, ticket_id in enumerate(ids):
        if n:
            print()
        run_ticket(db, get_ticket(ticket_id), make_model(ticket_id, args.live))


def cmd_changes(args) -> None:
    rows = shop.list_changes(shop.connect())
    if not rows:
        print("no changes since reset")
        return
    print("changes since reset")
    for row in rows:
        print(f"{row['run_id']}  {row['kind']:<8}{row['target']:<8}{row['detail']}")


def cmd_tools(args) -> None:
    print(f"{'tool':<16}{'kind':<7}{'risk':<8}{'scope':<17}undo")
    for spec in REGISTRY.values():
        print(f"{spec.name:<16}{spec.kind:<7}{spec.risk:<8}{spec.scope:<17}"
              f"{spec.undo}")


def parse_args(pairs: list[str]) -> dict:
    """key=value pairs from the command line; numbers become floats."""
    args = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        try:
            args[key] = float(value)
        except ValueError:
            args[key] = value
    return args


def cmd_check(args) -> None:
    """Ask the guard about one call, without running it."""
    call = Call(args.tool, parse_args(args.args))
    me = Identity("sam", "check", "-", "-", args.requester)
    print(f"check {show_call(call)} {me.label()}")
    for engine in guard.ENGINES:
        decision = guard.check(shop.connect(), me, call, engine)
        print(f"{engine:<8}{decision.effect} · rule {decision.rule}")
    print(f"{'why':<8}{decision.reason}")
    if args.explain:
        explain(me, call)


def explain(me: Identity, call: Call) -> None:
    """What the guard decided from: the facts it gathered, and the Cedar request."""
    facts = guard.gather_facts(shop.connect(), me, call)
    width = max(len(key) for key in facts) + 2
    print("\nfacts the guard gathered")
    for key, value in facts.items():
        print(f"  {key:<{width}}{value}")
    request, entities = cedar_policy.to_request(facts)
    print("\ncedar request")
    for key in ("principal", "action", "resource"):
        print(f"  {key:<11}{request[key]}")
    show_attrs("context", request["context"])
    for e in entities:
        show_attrs(f"entity {cedar_value({'__entity': e['uid']})}", e["attrs"])


def show_attrs(title: str, attrs: dict) -> None:
    print(f"  {title}")
    for key, value in attrs.items():
        print(f"    {key} = {cedar_value(value)}")


def cedar_value(value) -> str:
    """A value as Cedar writes it: Customer::"C-102", "open", 2000."""
    if isinstance(value, dict) and "__entity" in value:
        return f'{value["__entity"]["type"]}::"{value["__entity"]["id"]}"'
    return json.dumps(value)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bluekite", description="Sam at Blue Kite")
    p.add_argument("--live", action="store_true", help="use a live model endpoint")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("reset", help="rebuild the shop database").set_defaults(
        func=cmd_reset)
    sub.add_parser("tickets", help="list the practice tickets").set_defaults(
        func=cmd_tickets)
    run = sub.add_parser("run", help="let Sam work on tickets")
    run.add_argument("tickets", nargs="*")
    run.add_argument("--all", action="store_true")
    run.set_defaults(func=cmd_run)
    sub.add_parser("tools", help="Sam's tools, from the registry").set_defaults(
        func=cmd_tools)
    check = sub.add_parser("check", help="ask the guard about one tool call")
    check.add_argument("tool")
    check.add_argument("args", nargs="*", help="key=value")
    check.add_argument("--for", dest="requester", help="customer id, e.g. C-102")
    check.add_argument("--explain", action="store_true",
                       help="also show the facts and the Cedar request")
    check.set_defaults(func=cmd_check)
    sub.add_parser("changes", help="what changed since the reset").set_defaults(
        func=cmd_changes)
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    args.func(args)
