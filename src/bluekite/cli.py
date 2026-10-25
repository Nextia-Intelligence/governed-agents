"""The `bluekite` command."""

import argparse

from bluekite import shop
from bluekite.tickets import get_ticket, load_tickets


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
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("reset", help="rebuild the shop database").set_defaults(
        func=cmd_reset)
    sub.add_parser("tickets", help="list the practice tickets").set_defaults(
        func=cmd_tickets)
    sub.add_parser("changes", help="what changed since the reset").set_defaults(
        func=cmd_changes)
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    args.func(args)
