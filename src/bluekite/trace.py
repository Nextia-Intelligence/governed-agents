"""The short trace a run prints. Repeated identical steps are folded into one line."""

from bluekite.model import Call, cost


def show_args(args: dict) -> str:
    parts = []
    for key, value in args.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.2f}")
        else:
            parts.append(f"{key}={value!r}".replace("'", '"'))
    return ", ".join(parts)


def show_call(call: Call) -> str:
    return f"{call.tool}({show_args(call.args)})"


class Trace:
    def __init__(self, out=print):
        self.out = out
        self.last = None  # the last (call, result) pair we printed
        self.folded = 0  # how many times it repeated since

    def line(self, text: str) -> None:
        self._flush()
        self.out(text)

    def step(self, call: Call, result) -> None:
        # A blocked call has its own mark (✋, ⏸ or ⛔); a result gets "← ".
        blocked = result.status in ("denied", "paused", "stopped")
        summary = result.summary if blocked else f"← {result.summary}"
        pair = (show_call(call), summary)
        if pair == self.last and not result.note:
            self.folded += 1
            return
        self.line(f"→ {pair[0]}")
        if result.note:
            self.out(result.note)
        self.out(pair[1])
        self.last = pair

    def _flush(self) -> None:
        if self.folded:
            times = "time" if self.folded == 1 else "times"
            self.out(f"  ↻ same call, same result · {self.folded} more {times}")
        self.folded = 0
        self.last = None

    def footer(self, steps: int, tokens: int, extra: str = "") -> None:
        self.line(f"steps {steps} · tokens {tokens:,} · cost ${cost(tokens):.3f}"
                  + extra)
