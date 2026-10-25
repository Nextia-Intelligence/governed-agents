"""Build an evidence pack: each control, its code, its tests, sample audit events,
and the framework items it relates to (by name and link only, no legal advice)."""

import inspect
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bluekite import shop_api
from bluekite.governance import (approvals, audit, budgets, credentials, guard,
                                 identity, policy, registry, untrusted)

ROOT = Path(__file__).parents[3]
EU_AI_ACT = "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"
OWASP = "https://genai.owasp.org/llm-top-10/"
FRAMEWORKS = {  # key: (short name, full name, link)
    "eu-9": ("EU AI Act Art. 9", "EU AI Act, Article 9: Risk management system",
             EU_AI_ACT),
    "eu-12": ("EU AI Act Art. 12", "EU AI Act, Article 12: Record-keeping", EU_AI_ACT),
    "eu-14": ("EU AI Act Art. 14", "EU AI Act, Article 14: Human oversight", EU_AI_ACT),
    "eu-15": ("EU AI Act Art. 15",
              "EU AI Act, Article 15: Accuracy, robustness and cybersecurity",
              EU_AI_ACT),
    "nist": ("NIST AI RMF",
             "NIST AI RMF 1.0, with its Generative AI Profile NIST AI 600-1",
             "https://www.nist.gov/itl/ai-risk-management-framework"),
    "iso": ("ISO/IEC 42001", "ISO/IEC 42001: AI management system",
            "https://www.iso.org/standard/42001"),
    "llm01": ("OWASP LLM01", "OWASP Top 10 for LLM Applications 2025: LLM01 Prompt "
              "Injection", OWASP),
    "llm02": ("OWASP LLM02", "OWASP Top 10 for LLM Applications 2025: LLM02 "
              "Sensitive Information Disclosure", OWASP),
    "llm06": ("OWASP LLM06", "OWASP Top 10 for LLM Applications 2025: LLM06 "
              "Excessive Agency", OWASP),
    "llm10": ("OWASP LLM10", "OWASP Top 10 for LLM Applications 2025: LLM10 "
              "Unbounded Consumption", OWASP),
}


@dataclass(frozen=True)
class Control:
    name: str
    what: str
    code: tuple  # functions and classes that do the work
    tests: tuple[str, ...]  # test files
    sample: tuple[str, str | None]  # an audit event to show: its kind and effect
    frameworks: tuple[str, ...]


CONTROLS = (
    Control("Identity and least privilege",
            "Every run has an agent id, a run id and the customer it acts for, taken "
            "from the sender's address. Each tool gets one scoped credential.",
            (identity.identify, registry.validate, credentials.require,
             shop_api.refund),
            ("tests/test_least_privilege.py",), ("start", None),
            ("llm06", "eu-15", "nist")),
    Control("Policy as code",
            "One guard checks every tool call against rules in Python and Cedar. "
            "If the guard fails, it denies.",
            (guard.check, policy.evaluate), ("tests/test_policy.py",),
            ("call", "deny"), ("llm06", "eu-9", "nist")),
    Control("Human approval",
            "High-risk calls wait for a person. The approval is bound to a hash of "
            "the exact arguments and it expires.",
            (approvals.request, approvals.for_call), ("tests/test_approvals.py",),
            ("call", "ask"), ("eu-14", "llm06", "nist")),
    Control("Budgets and stopping",
            "Step, time and cost limits, a loop detector and a kill switch, checked "
            "before every turn and every call. Errors stop the run.",
            (budgets.before_turn, budgets.before_call), ("tests/test_budgets.py",),
            ("call", "stop"), ("llm10", "nist")),
    Control("Untrusted input",
            "Ticket text and tool results are wrapped as data. A detector flags "
            "injections; the guard still decides on the action.",
            (untrusted.wrap, untrusted.scan), ("tests/test_untrusted.py",),
            ("flag", None), ("llm01", "eu-15")),
    Control("Audit trail",
            "One JSON event per step, hash-chained, with personal data redacted. "
            "Runs can be verified and replayed.",
            (audit.record, audit.verify, audit.redact), ("tests/test_audit.py",),
            ("end", None), ("eu-12", "llm02", "iso", "nist")),
    Control("Tested controls and a release gate",
            "Governance tests and an attack suite run in CI. A failing control "
            "blocks the release.",
            (), ("tests/test_governance.py", "tests/attacks/test_attacks.py",
                 ".github/workflows/governance.yml"),
            ("", None), ("eu-9", "iso", "nist")),
)


def code_refs(control: Control) -> list[str]:
    """Where the control lives: file and line range, read from the code itself."""
    refs = []
    for item in control.code:
        lines, first = inspect.getsourcelines(item)
        path = Path(inspect.getsourcefile(item)).relative_to(ROOT)
        refs.append(f"`{path}` lines {first}-{first + len(lines) - 1}: "
                    f"`{item.__name__}`")
    return refs


def tests_in(path: str) -> list[str]:
    text = (ROOT / path).read_text()
    return re.findall(r"^def (test_\w+)", text, re.MULTILINE)


def sample_event(events: list[dict], kind: str, effect: str | None) -> dict | None:
    for event in events:
        if event["kind"] == kind and (
                effect is None or event.get("decided", {}).get("effect") == effect):
            return event
    return None


def run_tests() -> str:
    """Run the tests now, so the pack says whether they pass."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "the tests did not run"
    return re.sub(r" in [\d.]+s", "", summary.strip("= "))


def render_control(n: int, control: Control, events: list[dict]) -> list[str]:
    out = [f"## {n}. {control.name}", "", control.what, ""]
    if control.code:  # the release gate has tests and a workflow, no code
        out += ["**Code**", ""] + [f"- {ref}" for ref in code_refs(control)] + [""]
    out += ["**Tests**", ""]
    for path in control.tests:
        names = tests_in(path) if path.endswith(".py") else []
        count = f" ({len(names)} test functions)" if names else ""
        out.append(f"- `{path}`{count}")
    event = sample_event(events, *control.sample) if control.sample[0] else None
    if event:
        out += ["", "**Sample audit event**", "", "```json",
                json.dumps(event, ensure_ascii=False, indent=2), "```"]
    out += ["", "**Related framework items** (name and link only)", ""]
    out += [f"- [{FRAMEWORKS[key][1]}]({FRAMEWORKS[key][2]})"
            for key in control.frameworks]
    return out + [""]


def summary_table() -> list[str]:
    out = ["| # | Control | Tests | Framework items |", "|---|---|---|---|"]
    for n, c in enumerate(CONTROLS, start=1):
        tests = ", ".join(f"`{Path(t).name}`" for t in c.tests)
        items = ", ".join(FRAMEWORKS[key][0] for key in c.frameworks)
        out.append(f"| {n} | {c.name} | {tests} | {items} |")
    return out + [""]


def build(run_the_tests: bool = True) -> tuple[str, dict]:
    """The evidence pack as Markdown, and a few numbers for the command line."""
    events = audit.read_events()
    chain_ok, chain = audit.verify()
    tests = run_tests() if run_the_tests else "not run"
    out = ["# Evidence pack: Sam, the Blue Kite support agent", "",
           "Made by `bluekite evidence` from the code, the tests and the audit log.",
           "This is not legal advice. Framework items are named and linked so a "
           "reviewer can find them. Whether a control meets an obligation is for "
           "your legal and compliance people to decide.", "",
           f"- Tests: {tests}", f"- Audit log: {chain}", ""] + summary_table()
    for n, control in enumerate(CONTROLS, start=1):
        out += render_control(n, control, events)
    numbers = {"controls": len(CONTROLS), "tests": tests, "events": len(events),
               "chain_ok": chain_ok}
    return "\n".join(out), numbers


def write(run_the_tests: bool = True) -> tuple[Path, dict]:
    text, numbers = build(run_the_tests)
    path = ROOT / "evidence" / "EVIDENCE.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    return path, numbers
