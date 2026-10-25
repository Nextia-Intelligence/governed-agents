"""The `bluekite` command."""

import argparse

import json
import os
from dataclasses import replace

from bluekite import shop
from bluekite.clock import FIXED
from bluekite.agent import resume_run, run_ticket
from bluekite.governance import approvals, audit, budgets, cedar_policy, guard
from bluekite.governance.replay import replay
from bluekite.governance.identity import Identity
from bluekite.governance.registry import REGISTRY
from bluekite.model import Call, cost
from bluekite.trace import show_call
from bluekite.model import LiveModel, ReplayModel
from bluekite.tickets import get_ticket, load_tickets, prepare


def make_model(ticket_id: str, live: bool):
    return LiveModel() if live else ReplayModel(ticket_id)


def cmd_reset(args) -> None:
    shop.reset()
    print("reset: 3 customers, 4 orders, no refunds, no changes")


def cmd_tickets(args) -> None:
    tickets = load_tickets(args.variants)
    width = max(len(ticket_id) for ticket_id in tickets) + 2  # ids never touch emails
    for ticket in tickets.values():
        text = ticket["text"].splitlines()[0]
        text = text if len(text) <= 46 else text[:45] + "…"  # short enough for a video
        print(f"{ticket['id']:<{width}}{ticket['from']:<26}{text}")


def cmd_run(args) -> None:
    ids = list(load_tickets()) if args.all else args.tickets
    if not ids:
        raise SystemExit("give a ticket id, or --all")
    set_limits(args)
    db = shop.connect()
    for n, ticket_id in enumerate(ids):
        if n:
            print()
        ticket = get_ticket(ticket_id)
        prepare(db, ticket)
        run_ticket(db, ticket, make_model(ticket_id, args.live))


def set_limits(args) -> None:
    """Limits for this command only, e.g. bluekite run T-1005 --max-steps 3."""
    changes = {"steps_per_run": args.max_steps, "seconds_per_run": args.max_seconds,
               "cost_per_run": args.max_cost}
    changes = {key: value for key, value in changes.items() if value is not None}
    budgets.LIMITS = replace(budgets.LIMITS, **changes)


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
    print("\nargs hash (what an approval of this call is bound to)")
    print(f"  sha256 {approvals.args_hash(call)}")


def show_attrs(title: str, attrs: dict) -> None:
    print(f"  {title}")
    for key, value in attrs.items():
        print(f"    {key} = {cedar_value(value)}")


def cedar_value(value) -> str:
    """A value as Cedar writes it: Customer::"C-102", "open", 2000."""
    if isinstance(value, dict) and "__entity" in value:
        return f'{value["__entity"]["type"]}::"{value["__entity"]["id"]}"'
    return json.dumps(value)


def cmd_approvals(args) -> None:
    found = approvals.list_all(shop.connect(), args.all)
    if not found:
        print("no approvals" if args.all else "no pending approvals")
    for n, approval in enumerate(found):
        if n:
            print()
        show_approval(approval)


def show_approval(a: dict) -> None:
    """What the approver sees: who, what, why, the evidence, and what it binds."""
    call = Call(a["tool"], json.loads(a["args"]))
    print(f"{a['id']}  {a['status']:<10}run {a['run_id']} · {a['agent']} for "
          f"{a['on_behalf_of']} · ticket {a['ticket_id']}")
    print(f"  what      {show_call(call)}")
    print(f"  why       rule {a['rule']}")
    print(f"            {a['reason']}")
    for n, fact in enumerate(json.loads(a["evidence"])):
        print(f"  {'evidence' if n == 0 else '':<10}{fact}")
    expires = a["expires_at"].replace("T", " ")[:16]
    print(f"  binds     args sha256 {a['args_hash'][:12]} · expires {expires}")
    if a["decided_by"]:
        decision = "rejected" if a["status"] == "rejected" else "approved"
        print(f"  decided   {decision} by {a['decided_by']}")
    if a["used_at"]:
        print(f"  used      once, by run {a['run_id']} · it cannot be used again")


def cmd_decide(args) -> None:
    status = "approved" if args.command == "approve" else "rejected"
    try:
        approval = approvals.decide(shop.connect(), args.id, status, args.by)
    except approvals.ApprovalError as error:
        raise SystemExit(str(error))
    call = Call(approval["tool"], json.loads(approval["args"]))
    print(f"{approval['id']} {status} by {args.by} · {show_call(call)}")
    print(f"next: bluekite resume {approval['run_id']}")


def cmd_resume(args) -> None:
    set_limits(args)
    db = shop.connect()
    ticket_id = json.loads(db.execute(
        "select ticket from runs where id = ?", (args.run,)).fetchone()[0])["id"]
    resume_run(db, args.run, make_model(ticket_id, args.live))


def cmd_kill(args) -> None:
    budgets.kill(shop.connect(), args.agent, args.by)
    print(f"kill switch on for {args.agent} · every run stops before its next step")


def cmd_unkill(args) -> None:
    budgets.unkill(shop.connect(), args.agent)
    print(f"kill switch off for {args.agent}")


def cmd_budget(args) -> None:
    db, limits = shop.connect(), budgets.LIMITS
    spent = cost(budgets.spent_today(db, args.agent))
    kill = budgets.killed(db, args.agent)
    print(f"budget for {args.agent}")
    print(f"  steps per run   {limits.steps_per_run}")
    print(f"  time per run    {limits.seconds_per_run} s")
    print(f"  cost per run    ${limits.cost_per_run:.3f}")
    print(f"  cost per day    ${limits.cost_per_day:.2f} · spent today ${spent:.3f}")
    print(f"  same call       at most {limits.same_call_max} times in a run")
    print(f"  kill switch     {'on · ' + kill.reason if kill else 'off'}")


def cmd_audit(args) -> None:
    if args.target == "verify":
        ok, message = audit.verify()
        print(f"audit log {message}")
        raise SystemExit(0 if ok else 1)
    events = audit.for_run(args.target)
    if not events:
        raise SystemExit(f"no audit events for {args.target}")
    for event in events:
        print(f"#{event['seq']:<4}{event['kind']:<7}{describe(event)} · "
              f"{event['hash'][:8]}")


def describe(e: dict) -> str:
    """One short line per audit event."""
    if e["kind"] in ("start", "resume"):
        return f"{e['agent']} for {e['for'] or 'unknown sender'} · ticket {e['ticket']}"
    if e["kind"] == "call":
        d = e["decided"]
        rule = "" if d["effect"] == "allow" else f" {d['rule']}"
        return f"{e['tool']} · {d['by']} {d['effect']}{rule} · {e['status']}"
    if e["kind"] == "flag":
        return f"{e['source']} · {', '.join(e['found'])}"
    if e["kind"] == "decide":
        return (f"{e['approval']} {e['decision']} by {e['by']} · {e['tool']} · "
                f"args {e['args_hash'][:12]}")
    if e["kind"] == "stop":
        return f"{e['decided']['by']} {e['decided']['rule']}"
    if e["kind"] == "reply":
        return e["text"] if len(e["text"]) <= 44 else e["text"][:43] + "…"
    return (f"{e['status']} · steps {e['steps']} · tokens {e['tokens']:,} · "
            f"cost ${e['cost']:.3f}")


def cmd_replay(args) -> None:
    events = audit.for_run(args.run)
    if not events:
        raise SystemExit(f"no audit events for {args.run}")
    ok, _ = audit.verify()
    print(f"replay of run {args.run} · {len(events)} audit events · "
          f"chain {'intact' if ok else 'BROKEN'}")
    replay(events)


def command(sub, name: str, func, text: str) -> argparse.ArgumentParser:
    cmd = sub.add_parser(name, help=text)
    cmd.set_defaults(func=func)
    return cmd


def add_shop_commands(sub) -> None:
    command(sub, "reset", cmd_reset, "rebuild the shop database")
    tickets = command(sub, "tickets", cmd_tickets, "list the practice tickets")
    tickets.add_argument("--variants", action="store_true", help="also variants")
    run = command(sub, "run", cmd_run, "let Sam work on tickets")
    run.add_argument("tickets", nargs="*")
    run.add_argument("--all", action="store_true")
    add_limit_options(run)
    command(sub, "changes", cmd_changes, "what changed since the reset")


def add_limit_options(cmd) -> None:
    """Change a limit for this command only: steps, seconds or dollars per run."""
    cmd.add_argument("--max-steps", type=int, metavar="N", help="steps per run")
    cmd.add_argument("--max-seconds", type=int, metavar="S", help="seconds per run")
    cmd.add_argument("--max-cost", type=float, metavar="USD", help="dollars per run")


def add_guard_commands(sub) -> None:
    command(sub, "tools", cmd_tools, "Sam's tools, from the registry")
    check = command(sub, "check", cmd_check, "ask the guard about one tool call")
    check.add_argument("tool")
    check.add_argument("args", nargs="*", help="key=value")
    check.add_argument("--for", dest="requester", help="customer id, e.g. C-102")
    check.add_argument("--explain", action="store_true",
                       help="also show the facts, the Cedar request and the args hash")


def add_approval_commands(sub) -> None:
    queue = command(sub, "approvals", cmd_approvals, "the approval queue")
    queue.add_argument("--all", action="store_true", help="also decided ones")
    for name in ("approve", "reject"):
        decide = command(sub, name, cmd_decide, f"{name} a pending approval")
        decide.add_argument("id")
        decide.add_argument("--by", default="support-lead", help="who decides")
    resume = command(sub, "resume", cmd_resume, "go on with a paused run")
    resume.add_argument("run")
    add_limit_options(resume)


def add_budget_commands(sub) -> None:
    for name, func, text in (("kill", cmd_kill, "stop an agent now"),
                             ("unkill", cmd_unkill, "let a stopped agent run")):
        switch = command(sub, name, func, text)
        switch.add_argument("agent")
        switch.add_argument("--by", default="support-lead", help="who")
    budget = command(sub, "budget", cmd_budget, "limits and spend for an agent")
    budget.add_argument("agent", nargs="?", default="sam")


def add_audit_commands(sub) -> None:
    log = command(sub, "audit", cmd_audit, "show a run's audit events, or verify")
    log.add_argument("target", help="a run id, or: verify")
    again = command(sub, "replay", cmd_replay, "replay a run from the audit log")
    again.add_argument("run")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bluekite", description="Sam at Blue Kite")
    p.add_argument("--live", action="store_true", help="use a live model endpoint")
    p.add_argument("--clock", help="a fixed time, e.g. 2026-10-25T10:00:00")
    sub = p.add_subparsers(dest="command", required=True)
    add_shop_commands(sub)
    add_guard_commands(sub)
    add_approval_commands(sub)
    add_budget_commands(sub)
    add_audit_commands(sub)
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    # Replay mode uses a fixed clock (stable output); live mode the real time.
    if args.clock or "BLUEKITE_CLOCK" not in os.environ:
        os.environ["BLUEKITE_CLOCK"] = args.clock or ("real" if args.live else FIXED)
    args.func(args)
