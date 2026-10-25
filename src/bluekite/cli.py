"""The `bluekite` command."""

import argparse

from bluekite import shop
from bluekite.agent import run_ticket
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
    sub.add_parser("changes", help="what changed since the reset").set_defaults(
        func=cmd_changes)
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    args.func(args)
