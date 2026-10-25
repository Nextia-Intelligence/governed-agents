"""Governance tests: is every control there, and is it wired in?"""

from pathlib import Path

from bluekite import shop, tools
from bluekite.governance import audit, guard, policy
from bluekite.governance.cedar_policy import POLICY_FILE
from bluekite.governance.policy import Decision
from bluekite.governance.registry import REGISTRY
from bluekite.tickets import load_tickets


def test_registry_tools_and_policy_agree():
    assert set(REGISTRY) == set(tools.TOOLS) == set(policy.SAMS_TOOLS)


# For each high-risk tool, the rule that brings in a person.
ASK_RULES = {"issue_refund": "refund-over-25-needs-human",
             "close_account": "close-account-needs-human"}


def test_every_high_risk_tool_can_ask_for_a_person():
    cedar = POLICY_FILE.read_text()
    asks = {rule.id for rule in policy.RULES if rule.effect == "ask"}
    for spec in REGISTRY.values():
        if spec.risk == "high":
            assert ASK_RULES[spec.name] in asks
            assert f'@id("{ASK_RULES[spec.name]}")' in cedar


def test_tools_write_only_through_the_scoped_api():
    source = Path(tools.__file__).read_text()
    for write in ("shop.refund(", "shop.close(", "shop.set_address("):
        assert write not in source, f"tools.py calls {write} without a token"


def test_no_tool_runs_without_the_guard(replay, db, monkeypatch):
    def deny_everything(db, identity, call, engine=None):
        return Decision("deny", "test-deny-all", "testing")

    ran, call_tool = [], tools.call_tool

    def spy(ctx, tool, args):
        ran.append(tool)
        return call_tool(ctx, tool, args)

    monkeypatch.setattr(guard, "check", deny_everything)
    monkeypatch.setattr(tools, "call_tool", spy)
    for ticket_id in load_tickets(variants=True):  # every ticket, read tools too
        replay(ticket_id)
    assert ran == []
    assert shop.list_refunds(db) == []


def test_every_tool_call_is_in_the_audit_log(replay):
    for ticket_id in ("T-1001", "T-1004", "T-1005"):
        run, lines = replay(ticket_id)
        calls = [e for e in audit.for_run(run.identity.run_id) if e["kind"] == "call"]
        shown = [line for line in lines if line.startswith("→")]
        folded = sum(int(line.split("·")[1].split()[0]) for line in lines
                     if line.strip().startswith("↻"))
        assert len(calls) == len(shown) + folded
