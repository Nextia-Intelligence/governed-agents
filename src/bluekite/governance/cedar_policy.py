"""The same rules in Cedar (policies/sam.cedar), checked with cedarpy."""

import json
from pathlib import Path

import cedarpy

from bluekite.governance.policy import REASONS, Decision

POLICY_FILE = Path(__file__).parents[3] / "policies" / "sam.cedar"


def load_policies() -> tuple[str, dict]:
    """The policy text, and for each Cedar id ("policy3") its annotations."""
    text = POLICY_FILE.read_text()
    parsed = json.loads(cedarpy.policies_to_json_str(text))["staticPolicies"]
    return text, {pid: p.get("annotations", {}) for pid, p in parsed.items()}


def entity(kind: str, value: str) -> dict:
    return {"__entity": {"type": kind, "id": value}}


def to_request(facts: dict) -> tuple[dict, list]:
    context = {"amount_cents": facts.get("amount_cents", 0)}
    if facts["requester"]:
        context["requester"] = entity("Customer", facts["requester"])
    if "order_id" in facts:
        resource = f'Order::"{facts["order_id"]}"'
        attrs = {"owner": entity("Customer", facts["owner"] or "nobody"),
                 "refundable_cents": facts["refundable_cents"]}
        entities = [{"uid": {"type": "Order", "id": facts["order_id"]},
                     "attrs": attrs, "parents": []}]
    else:
        resource = f'Customer::"{facts.get("customer_id", "nobody")}"'
        entities = []
    request = {"principal": f'Agent::"{facts["agent"]}"',
               "action": f'Action::"{facts["tool"]}"',
               "resource": resource, "context": context}
    return request, entities


def evaluate(facts: dict) -> Decision:
    text, annotations = load_policies()
    request, entities = to_request(facts)
    result = cedarpy.is_authorized(request, text, entities)
    if result.diagnostics.errors:  # a policy that cannot be evaluated: fail closed
        return Decision("deny", "policy-error", str(result.diagnostics.errors[0]))
    if result.allowed:
        return Decision("allow", "sams-tools-only", "no rule stops this call")
    return explain(result.diagnostics.reasons, annotations, facts)


def explain(reasons: list[str], annotations: dict, facts: dict) -> Decision:
    """Which forbid decided? A real deny wins over an @effect("ask")."""
    if not reasons:  # no permit matched
        return Decision("deny", "sams-tools-only", "this is not one of Sam's tools")
    ordered = sorted(reasons, key=lambda pid: int(pid.removeprefix("policy")))
    asks = [pid for pid in ordered if annotations[pid].get("effect") == "ask"]
    denies = [pid for pid in ordered if pid not in asks]
    effect, pid = ("deny", denies[0]) if denies else ("ask", asks[0])
    rule = annotations[pid]["id"]
    return Decision(effect, rule, REASONS[rule].format(**facts))
