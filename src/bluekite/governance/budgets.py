"""Budgets and stopping: limits per run and per day, a loop detector, a kill switch."""

from dataclasses import dataclass

from bluekite import clock
from bluekite.model import Call, cost

TABLES = """
create table if not exists kills (agent text primary key, by text);
create table if not exists spend (day text, agent text, run_id text, tokens integer);
"""


@dataclass(frozen=True)
class Limits:
    steps_per_run: int = 10
    seconds_per_run: int = 60
    cost_per_run: float = 0.05  # dollars
    cost_per_day: float = 1.00  # dollars, for one agent
    same_call_max: int = 2  # the third identical call is a loop
    refunds_per_run: int = 2  # whatever the amounts are


LIMITS = Limits()


@dataclass(frozen=True)
class Stop:
    control: str  # "kill switch", "budget"
    reason: str  # for example "loop · the same call 3 times"

    def mark(self) -> str:
        if self.control == "kill switch":
            return f"⛔ kill switch: {self.reason}"
        return f"⛔ budget: stop · {self.reason}"


def before_turn(db, run) -> Stop | None:
    """Checked before every model turn. If we cannot check, we stop (fail closed)."""
    limits = LIMITS
    try:
        return (killed(db, run.identity.agent) or over_steps(run, limits)
                or over_time(run, limits) or over_cost(db, run, limits))
    except Exception as error:
        return Stop("budget", f"error · cannot check the budget: {error!r}")


def before_call(db, run, call: Call) -> Stop | None:
    """Checked before every tool call: the kill switch again, and loops."""
    limits = LIMITS
    try:
        return (killed(db, run.identity.agent) or looping(run, call, limits)
                or too_many_refunds(run, call, limits))
    except Exception as error:
        return Stop("budget", f"error · cannot check the budget: {error!r}")


def killed(db, agent: str) -> Stop | None:
    db.executescript(TABLES)
    row = db.execute("select by from kills where agent = ?", (agent,)).fetchone()
    return Stop("kill switch", f"{agent} is stopped by {row['by']}") if row else None


def over_steps(run, limits: Limits) -> Stop | None:
    if run.steps >= limits.steps_per_run:
        return Stop("budget", f"steps · {run.steps} of {limits.steps_per_run} used")
    return None


def over_time(run, limits: Limits) -> Stop | None:
    used = (clock.now() - clock.parse(run.started)).total_seconds()
    if used > limits.seconds_per_run:
        return Stop("budget", f"time · {used:.0f} s of {limits.seconds_per_run} s")
    return None


def over_cost(db, run, limits: Limits) -> Stop | None:
    if cost(run.tokens) > limits.cost_per_run:
        return Stop("budget", f"cost · ${cost(run.tokens):.3f} of "
                              f"${limits.cost_per_run:.3f} for this run")
    today = cost(spent_today(db, run.identity.agent))
    if today > limits.cost_per_day:
        return Stop("budget",
                    f"cost · ${today:.3f} of ${limits.cost_per_day:.2f} today")
    return None


def looping(run, call: Call, limits: Limits) -> Stop | None:
    """The same tool with the same arguments, again and again, is a loop."""
    same = [m for m in run.messages if m.get("call") == {"tool": call.tool,
                                                         "args": call.args}]
    if len(same) >= limits.same_call_max:
        return Stop("budget", f"loop · the same call {len(same) + 1} times")
    return None


def too_many_refunds(run, call: Call, limits: Limits) -> Stop | None:
    if call.tool != "issue_refund":
        return None
    done = [m for m in run.messages if m.get("call", {}).get("tool") == call.tool]
    if len(done) >= limits.refunds_per_run:
        return Stop("budget", f"refunds · {len(done) + 1} of "
                              f"{limits.refunds_per_run} per run")
    return None


def record_spend(db, run, tokens: int) -> None:
    db.executescript(TABLES)
    db.execute("insert into spend values (?,?,?,?)", (
        clock.now().date().isoformat(), run.identity.agent, run.identity.run_id,
        tokens))
    db.commit()


def spent_today(db, agent: str) -> int:
    db.executescript(TABLES)
    row = db.execute(
        "select coalesce(sum(tokens), 0) from spend where day = ? and agent = ?",
        (clock.now().date().isoformat(), agent))
    return row.fetchone()[0]


def kill(db, agent: str, by: str) -> None:
    db.executescript(TABLES)
    db.execute("insert or replace into kills values (?, ?)", (agent, by))
    db.commit()


def unkill(db, agent: str) -> None:
    db.executescript(TABLES)
    db.execute("delete from kills where agent = ?", (agent,))
    db.commit()
