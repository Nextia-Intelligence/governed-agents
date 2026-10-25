"""Write docs/LECTURE-RUNS.md: for every section tag, the commands a lecture shows,
their real output, and the code excerpts (file and line range) worth showing.

Run from the repository root:  python3 docs/make_lecture_runs.py
It checks out each tag in a temporary git worktree, so your working tree is safe.
"""

import ast
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "LECTURE-RUNS.md"

RESET_ALL = ["bluekite reset", "bluekite run --all"]

# tag: (title, [commands]). Each command runs in the tag's checkout, in order.
RUNS = {
    "s00": ("Welcome: set up the project", [
        "uv sync", "bluekite --help", "bluekite reset", "bluekite tickets",
        "uv run pytest -q"]),
    "s01": ("Why an agent needs governing: Sam, ungoverned", [
        "bluekite reset && bluekite run T-1001", "bluekite run T-1002",
        "bluekite run T-1003", "bluekite run T-1004", "bluekite run T-1005",
        "bluekite changes", "uv run pytest -q"]),
    "s02": ("Identity and least privilege", [
        "bluekite tools", *RESET_ALL, "bluekite changes", "uv run pytest -q",
        "uv run pytest exercises/check_s02.py -q --tb=no"]),
    "s02-solution": ("Exercise 2 solution", [
        "uv run pytest exercises/check_s02.py -q"]),
    "s03": ("Policy as code", [
        "bluekite reset",
        "bluekite check issue_refund order_id=O-5002 amount=2000 --for C-102",
        "bluekite check issue_refund order_id=O-5002 amount=2000",
        "bluekite check issue_refund order_id=O-5002 amount=20 --for C-102",
        "bluekite check issue_refund order_id=O-5003 amount=45 --for C-103",
        "bluekite check close_account customer_id=C-102 --for C-103",
        "bluekite check issue_refund order_id=O-5002 amount=2000 --for C-102 --explain",
        *RESET_ALL, "bluekite run T-1001",
        "bluekite reset && BLUEKITE_ENGINE=python bluekite run T-1001",
        "uv run pytest -q tests/test_policy.py", "uv run pytest -q",
        "uv run pytest exercises/check_s03.py -q --tb=no"]),
    "s03-solution": ("Exercise 3 solution", [
        "bluekite reset",
        "bluekite check issue_refund order_id=O-5002 amount=20 --for C-102 --explain",
        "uv run pytest exercises/check_s03.py -q"]),
    "s04": ("Human approval", [
        *RESET_ALL, "bluekite approvals", "bluekite approve A-0001",
        "bluekite resume r-0002", "bluekite approvals --all", "bluekite approve A-0001",
        "bluekite reset && bluekite run T-1002", "bluekite reject A-0001",
        "bluekite resume r-0001",
        "bluekite reset && bluekite run T-1002",
        "bluekite --clock 2026-10-25T11:30:00 approve A-0001",
        "bluekite reset && bluekite run T-1002", "bluekite approve A-0001",
        "bluekite --clock 2026-10-25T11:30:00 resume r-0001",
        "bluekite check close_account customer_id=C-103 --for C-103 --explain",
        "uv run pytest -q", "uv run pytest exercises/check_s04.py -q --tb=no"]),
    "s04-solution": ("Exercise 4 solution", [
        "bluekite reset && bluekite run T-1002",
        "bluekite approve A-0001 --by sam",
        "uv run pytest exercises/check_s04.py -q"]),
    "s05": ("Budgets and stopping", [
        "bluekite reset && bluekite run T-1005", "bluekite budget",
        "bluekite kill sam", "bluekite run T-1001", "bluekite budget",
        "bluekite unkill sam", "bluekite run T-1001",
        "bluekite reset && bluekite run T-1005 --max-steps 3",
        "bluekite run T-1005 --max-seconds 8", "bluekite run T-1001 --max-cost 0.005",
        "bluekite reset && bluekite run T-1002",
        "bluekite kill sam --by 'on-call engineer'", "bluekite approve A-0001",
        "bluekite unkill sam", "bluekite approve A-0001",
        "bluekite reset && BLUEKITE_ENGINE=opa bluekite run T-1001", "bluekite changes",
        "uv run pytest -q", "uv run pytest exercises/check_s05.py -q --tb=no"]),
    "s05-solution": ("Exercise 5 solution", [
        "bluekite budget", "uv run pytest exercises/check_s05.py -q"]),
    "s06": ("Untrusted input", [
        "bluekite reset && bluekite run T-1004", "bluekite run T-1004-note",
        "bluekite tickets --variants", "uv run pytest -q",
        "uv run pytest exercises/check_s06.py -q --tb=no"]),
    "s06-solution": ("Exercise 6 solution", [
        "uv run pytest exercises/check_s06.py -q"]),
    "s07": ("Audit trail", [
        *RESET_ALL, "bluekite audit r-0001", "bluekite audit r-0005",
        "bluekite audit verify", "bluekite replay r-0001", "bluekite replay r-0004",
        "bluekite approve A-0001", "bluekite resume r-0002", "bluekite audit r-0002",
        "grep '\"kind\": \"decide\"' state/audit.jsonl | python3 -m json.tool",
        "sed -n 3p state/audit.jsonl | python3 -m json.tool",
        "sed -i.bak 's/\"tokens\": 2490/\"tokens\": 249/' state/audit.jsonl",
        "bluekite audit verify", "uv run pytest -q",
        "uv run pytest exercises/check_s07.py -q --tb=no"]),
    "s07-solution": ("Exercise 7 solution", [
        "uv run pytest exercises/check_s07.py -q"]),
    "s08": ("Test the controls", [
        "uv run pytest -q", "uv run pytest -q tests/attacks",
        "uv run pytest -q tests/test_governance.py", *RESET_ALL,
        "bluekite approve A-0001", "bluekite resume r-0002", "bluekite metrics",
        "bluekite run T-1001-twice", "bluekite reset && bluekite run T-1001-twice",
        "bluekite tickets --variants",
        "uv run pytest exercises/check_s08.py -q --tb=no"]),
    "s08-solution": ("Exercise 8 solution", [
        "uv run pytest exercises/check_s08.py -q", "uv run pytest -q tests/attacks"]),
    "s09": ("From code to evidence", [
        *RESET_ALL, "bluekite evidence", "head -n 22 evidence/EVIDENCE.md",
        "sed -n '/^## 7\\./,/^\\*\\*Related/p' evidence/EVIDENCE.md",
        "grep -m 1 'NIST AI 600-1' evidence/EVIDENCE.md"]),
    "s10": ("Capstone: Kit", [
        "bluekite-capstone reset", "bluekite-capstone requests",
        "bluekite-capstone run --all", "bluekite-capstone changes",
        "uv run pytest -q capstone/checks --tb=no", "uv run pytest -q"]),
    "s10-solution": ("Capstone solution", [
        "bluekite-capstone reset", "bluekite-capstone run --all",
        "bluekite-capstone changes", "uv run pytest -q"]),
}

# tag: [(file, symbol)]. symbol: a function or class name, a Cedar @id, a JSON
# ticket id, or None for the whole file.
EXCERPTS = {
    "s00": [("src/bluekite/shop.py", None), ("src/bluekite/tickets.json", None)],
    "s01": [("src/bluekite/tools.py", "look_up_order"),
            ("src/bluekite/tools.py", "issue_refund"),
            ("src/bluekite/tools.py", "close_account"),
            ("src/bluekite/agent.py", "run_ticket"),
            ("src/bluekite/model.py", "ReplayModel"),
            ("src/bluekite/recordings/T-1001.json", None)],
    "s02": [("src/bluekite/governance/identity.py", "identify"),
            ("src/bluekite/governance/registry.py", "REGISTRY"),
            ("src/bluekite/governance/registry.py", "validate"),
            ("src/bluekite/governance/credentials.py", None),
            ("src/bluekite/shop_api.py", "refund"),
            ("src/bluekite/tools.py", "look_up_order"),
            ("src/bluekite/agent.py", "use_tool")],
    "s03": [("src/bluekite/agent.py", "use_tool"),
            ("src/bluekite/governance/guard.py", "check"),
            ("src/bluekite/governance/guard.py", "gather_facts"),
            ("src/bluekite/governance/policy.py", "RULES"),
            ("src/bluekite/governance/policy.py", "evaluate"),
            ("policies/sam.cedar", "refund-within-order-total"),
            ("policies/sam.cedar", "close-account-needs-human"),
            ("src/bluekite/governance/cedar_policy.py", "explain"),
            ("src/bluekite/cli.py", "explain"),
            ("tests/test_policy.py", "ROWS"),
            ("src/bluekite/recordings/T-1001.json", None)],
    "s04": [("src/bluekite/agent.py", "check_approval"),
            ("src/bluekite/governance/approvals.py", "args_hash"),
            ("src/bluekite/governance/approvals.py", "evidence"),
            ("src/bluekite/governance/approvals.py", "expire_if_late"),
            ("src/bluekite/governance/approvals.py", "use"),
            ("src/bluekite/agent.py", "resume_run"),
            ("src/bluekite/governance/policy.py", "ASK_ABOVE_CENTS")],
    "s05": [("src/bluekite/governance/budgets.py", "Limits"),
            ("src/bluekite/governance/budgets.py", "before_turn"),
            ("src/bluekite/governance/budgets.py", "looping"),
            ("src/bluekite/governance/budgets.py", "killed"),
            ("src/bluekite/agent.py", "work"),
            ("tests/test_budgets.py", "test_the_kill_switch_stops_a_running_agent"),
            ("src/bluekite/cli.py", "set_limits"),
            ("src/bluekite/governance/approvals.py", "decide")],
    "s06": [("src/bluekite/governance/untrusted.py", None),
            ("src/bluekite/agent.py", "first_messages"),
            ("src/bluekite/agent.py", "flag"),
            ("src/bluekite/variants.json", None),
            ("tests/test_untrusted.py", "test_a_flag_never_blocks_an_allowed_action")],
    "s07": [("src/bluekite/governance/audit.py", "record"),
            ("src/bluekite/governance/audit.py", "redact"),
            ("src/bluekite/governance/audit.py", "verify"),
            ("src/bluekite/recorder.py", "Recorder"),
            ("src/bluekite/governance/replay.py", "replay"),
            ("src/bluekite/governance/approvals.py", "record_decision")],
    "s08": [("tests/test_governance.py", None),
            ("tests/attacks/invariants.py", "refunds_within_what_was_sold"),
            ("tests/attacks/invariants.py", "INVARIANTS"),
            ("tests/attacks/test_attacks.py", None),
            (".github/workflows/governance.yml", None),
            ("src/bluekite/governance/metrics.py", "summarize")],
    "s09": [("src/bluekite/governance/evidence.py", "FRAMEWORKS"),
            ("src/bluekite/governance/evidence.py", "CONTROLS"),
            ("src/bluekite/governance/evidence.py", "build"),
            ("src/bluekite/governance/evidence.py", "render_control")],
    "s10": [("capstone/kit/tools.py", None), ("capstone/kit/agent.py", "run_request"),
            ("capstone/kit/supply.py", "pay"), ("capstone/checks/test_kit.py", None)],
    "s10-solution": [("capstone/kit/governance.py", "RULES"),
                     ("capstone/kit/agent.py", "use_tool"),
                     ("capstone/kit/agent.py", "KitRecorder")],
}


def sh(command: str, cwd: Path, env: dict) -> str:
    result = subprocess.run(command, shell=True, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.stdout.rstrip("\n")


def python_range(path: Path, name: str) -> tuple[int, int] | None:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            first = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            return first, node.end_lineno
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(getattr(t, "id", None) == name for t in targets):
                return node.lineno, node.end_lineno
    return None


def text_range(path: Path, name: str) -> tuple[int, int] | None:
    """A Cedar policy by its @id, or a JSON object by its "id", up to a blank line."""
    lines = path.read_text().splitlines()
    for n, line in enumerate(lines):
        if f'@id("{name}")' in line or f'"id": "{name}"' in line:
            end = n
            while end + 1 < len(lines) and lines[end + 1].strip():
                end += 1
            return n + 1, end + 1
    return None


def excerpt(tree: Path, file: str, name: str | None) -> str:
    path = tree / file
    if not path.exists():
        return f"- `{file}`: (missing at this tag)"
    if name is None:
        return f"- `{file}` (whole file, {len(path.read_text().splitlines())} lines)"
    found = python_range(path, name) if file.endswith(".py") else text_range(path, name)
    if found is None:
        return f"- `{file}`: `{name}` (not found)"
    return f"- `{file}` lines {found[0]}-{found[1]}: `{name}`"


def run_tag(tag: str) -> list[str]:
    title, commands = RUNS[tag]
    tree = Path(tempfile.mkdtemp(prefix=f"bk-{tag}-")).resolve()  # no /tmp symlink
    shutil.rmtree(tree)
    subprocess.run(["git", "worktree", "add", "--detach", "-q", str(tree), tag],
                   cwd=ROOT, check=True)
    try:
        env = {**os.environ, "PATH": f"{tree}/.venv/bin:{os.environ['PATH']}",
               "UV_PROJECT_ENVIRONMENT": str(tree / ".venv")}
        env.pop("BLUEKITE_HOME", None)
        env.pop("BLUEKITE_CLOCK", None)
        env.pop("VIRTUAL_ENV", None)
        if tag != "s00":  # s00 shows the first "uv sync" itself
            sh("uv sync -q", tree, env)
        out = [f"## `{tag}`: {title}", ""]
        for command in commands:
            output = sh(command, tree, env)
            output = output.replace(str(tree), "<repo>")
            out += ["```console", f"$ {command}", output, "```", ""] if output else \
                ["```console", f"$ {command}", "```", ""]
        if tag in EXCERPTS:
            out += ["Code to show:", ""]
            out += [excerpt(tree, f, n) for f, n in EXCERPTS[tag]]
            out.append("")
        return out
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT)


HEADER = """# Lecture runs

The exact commands for each section tag, with the output of real runs at that tag.
Made by `python3 docs/make_lecture_runs.py`; run it again after any change to the code.

- Commands run in a fresh checkout of the tag, inside the project's environment
  (`source .venv/bin/activate`; or put `uv run` in front of `bluekite`).
- Replay mode, the fixed clock (2026-10-25 10:00) and run ids from a counter make the
  output the same on every run. Only the time that pytest prints changes.
- "Code to show" lists file and line range at that tag.
"""


def main() -> None:
    out = [HEADER]
    for tag in RUNS:
        print(f"running {tag} ...")
        out += run_tag(tag)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    OUT.write_text(text.rstrip() + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
