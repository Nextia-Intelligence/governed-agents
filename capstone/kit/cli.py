"""The `bluekite-capstone` command: run Kit on its practice requests."""

import argparse
import json
from pathlib import Path

from bluekite import shop
from bluekite.model import ReplayModel
from kit import supply
from kit.agent import run_request

HERE = Path(__file__).parent


def load_requests() -> dict[str, dict]:
    return {t["id"]: t for t in json.loads((HERE / "tickets.json").read_text())}


def cmd_run(args) -> None:
    requests = load_requests()
    ids = list(requests) if args.all else args.requests
    db = shop.connect()
    for n, request_id in enumerate(ids):
        if n:
            print()
        model = ReplayModel(request_id, folder=HERE / "recordings")
        run_request(db, requests[request_id], model)


def cmd_changes(args) -> None:
    rows = shop.list_changes(shop.connect())
    print("changes since reset" if rows else "no changes since reset")
    for row in rows:
        print(f"{row['run_id']}  {row['kind']:<9}{row['target']:<10} {row['detail']}")


def cmd_reset(args) -> None:
    supply.reset()
    print("reset: 2 suppliers, 2 items in stock, 2 invoices, no payments")


def cmd_requests(args) -> None:
    for request in load_requests().values():
        text = request["text"] if len(request["text"]) <= 44 else \
            request["text"][:43] + "…"
        print(f"{request['id']}  {request['from']:<30}{text}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="bluekite-capstone", description="Kit")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("reset", help="rebuild the shop").set_defaults(func=cmd_reset)
    sub.add_parser("requests", help="list Kit's practice requests").set_defaults(
        func=cmd_requests)
    run = sub.add_parser("run", help="let Kit work on requests")
    run.add_argument("requests", nargs="*")
    run.add_argument("--all", action="store_true")
    run.set_defaults(func=cmd_run)
    sub.add_parser("changes", help="what changed since the reset").set_defaults(
        func=cmd_changes)
    args = p.parse_args(argv)
    args.func(args)
