"""The tool registry: what each tool is, how risky it is, which arguments it takes."""

import re
from dataclasses import dataclass

ORDER_ID = {"type": "string", "pattern": r"^O-\d{4}$"}
CUSTOMER_ID = {"type": "string", "pattern": r"^C-\d{3}$"}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str  # "read" or "write"
    risk: str  # "low", "medium" or "high"
    scope: str  # the one credential scope this tool gets
    undo: str  # can we undo it?
    description: str
    params: dict  # argument name -> JSON schema


REGISTRY = {spec.name: spec for spec in [
    ToolSpec("look_up_order", "read", "low", "orders:read", "nothing to undo",
             "Look up an order by its id.", {"order_id": ORDER_ID}),
    ToolSpec("change_address", "write", "medium", "customers:write",
             "yes, change it back", "Change the address of a customer.",
             {"customer_id": CUSTOMER_ID,
              "address": {"type": "string", "minLength": 5, "maxLength": 80,
                          "pattern": r"^[^<>\n]+$"}}),
    ToolSpec("issue_refund", "write", "high", "refunds:write",
             "no, the money is gone", "Refund an amount in dollars on an order.",
             {"order_id": ORDER_ID,
              "amount": {"type": "number", "exclusiveMinimum": 0, "maximum": 5000}}),
    ToolSpec("close_account", "write", "high", "accounts:close",
             "no, data deleted after 30 days", "Close a customer's account.",
             {"customer_id": CUSTOMER_ID}),
]}


def validate(spec: ToolSpec, args: dict) -> list[str]:
    """Check the arguments against the schema. Returns a list of problems."""
    problems = [f"unknown argument {key}" for key in args if key not in spec.params]
    for key, rule in spec.params.items():
        if key not in args:
            problems.append(f"missing {key}")
        else:
            problems += check_value(key, args[key], rule)
    return problems


def check_value(key: str, value, rule: dict) -> list[str]:
    if rule["type"] == "string":
        if not isinstance(value, str):
            return [f"{key} must be a string"]
        if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
            return [f"{key} {value!r} does not match {rule['pattern']}"]
        if len(value) < rule.get("minLength", 0):
            return [f"{key} is too short"]
        if len(value) > rule.get("maxLength", len(value)):
            return [f"{key} is too long"]
        return []
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return [f"{key} must be a number"]
    if "exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"]:
        return [f"{key} must be more than {rule['exclusiveMinimum']}"]
    if "maximum" in rule and value > rule["maximum"]:
        return [f"{key} must be at most {rule['maximum']}"]
    return []


def openai_schemas() -> list[dict]:
    """The registry in the function-calling format, for the live model."""
    return [{"type": "function", "function": {
        "name": spec.name, "description": spec.description,
        "parameters": {"type": "object", "properties": spec.params,
                       "required": list(spec.params),
                       "additionalProperties": False}}}
            for spec in REGISTRY.values()]
