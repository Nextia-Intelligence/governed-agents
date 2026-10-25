"""The short trace a run prints. Repeated identical steps are folded into one line."""

from bluekite.model import Call, cost


def arg_parts(args: dict) -> list[str]:
    parts = []
    for key, value in args.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.2f}")
        elif isinstance(value, str) and len(value) > 36:  # keep the trace short
            parts.append(f'{key}="{value[:35]}…"')
        else:
            parts.append(f"{key}={value!r}".replace("'", '"'))
    return parts


def show_args(args: dict) -> str:
    return ", ".join(arg_parts(args))


def show_call(call: Call) -> str:
    return f"{call.tool}({show_args(call.args)})"


def call_lines(call: Call, width: int = 80) -> list[str]:
    """The call after "→ ", broken after a comma when it is too wide for the video."""
    parts = arg_parts(call.args)
    if not parts:
        return [f"→ {call.tool}()"]
    lines, current = [], f"→ {call.tool}("
    indent = " " * len(current)
    for n, part in enumerate(parts):
        end = ")" if n == len(parts) - 1 else ", "
        too_wide = len(current) + len(part) + len(end) > width
        if too_wide and not current.endswith("("):
            lines.append(current.rstrip())
            current = indent
        current += part + end
    return lines + [current]


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
        first, *rest = call_lines(call)
        self.line(first)
        for more in rest:
            self.out(more)
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
