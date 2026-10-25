"""The model behind Sam: recorded answers (replay, the default) or a live endpoint."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

RECORDINGS = Path(__file__).parent / "recordings"
PRICE_PER_MILLION_TOKENS = 6.00  # dollars, the same price for replay and live


@dataclass
class Call:
    tool: str
    args: dict


@dataclass
class Turn:
    """One answer from the model: a tool call, or a final text for the customer."""

    call: Call | None
    text: str | None
    tokens: int


def cost(tokens: int) -> float:
    return tokens * PRICE_PER_MILLION_TOKENS / 1_000_000


class Model(Protocol):
    def next(self, messages: list[dict], tools: list[dict]) -> Turn: ...


class ReplayModel:
    """Plays back a recording by hand: no network, no API key, the same every run.

    A recording is a list of turns. A turn may have "repeat" (play it n times)
    and "if_denied" (the turns to play when its tool call was refused).
    """

    def __init__(self, recording: str):
        data = json.loads((RECORDINGS / f"{recording}.json").read_text())
        self.turns = expand(data["turns"])

    def next(self, messages: list[dict], tools: list[dict]) -> Turn:
        turns, i = self.turns, 0
        for message in messages:
            if message["role"] != "tool" or i >= len(turns):
                continue
            if message["status"] == "denied" and "if_denied" in turns[i]:
                turns, i = turns[i]["if_denied"], 0
            else:
                i += 1
        if i >= len(turns):
            return Turn(None, "I could not finish this ticket.", 0)
        return to_turn(turns[i])


def expand(turns: list[dict]) -> list[dict]:
    out = []
    for turn in turns:
        if "if_denied" in turn:
            turn = {**turn, "if_denied": expand(turn["if_denied"])}
        out.extend([turn] * turn.get("repeat", 1))
    return out


def to_turn(raw: dict) -> Turn:
    if "call" in raw:
        call = Call(raw["call"]["tool"], raw["call"]["args"])
        return Turn(call, None, raw["tokens"])
    return Turn(None, raw["say"], raw["tokens"])


class LiveModel:
    """Any OpenAI-compatible endpoint. Needs the extra: uv sync --extra live."""

    def __init__(self):
        from openai import OpenAI  # imported here, so replay needs no openai

        self.client = OpenAI(base_url=os.environ.get("BLUEKITE_BASE_URL"),
                             api_key=os.environ["BLUEKITE_API_KEY"])
        self.name = os.environ.get("BLUEKITE_MODEL", "gpt-4o-mini")

    def next(self, messages: list[dict], tools: list[dict]) -> Turn:
        reply = self.client.chat.completions.create(
            model=self.name, messages=to_openai(messages), tools=tools,
            parallel_tool_calls=False)
        message = reply.choices[0].message
        tokens = reply.usage.total_tokens if reply.usage else 0
        if message.tool_calls:
            first = message.tool_calls[0].function
            return Turn(Call(first.name, json.loads(first.arguments)), None, tokens)
        return Turn(None, message.content or "", tokens)


def to_openai(messages: list[dict]) -> list[dict]:
    """Our simple message list, in the shape the OpenAI API expects."""
    out = []
    for m in messages:
        if m["role"] == "assistant" and "call" in m:
            function = {"name": m["call"]["tool"],
                        "arguments": json.dumps(m["call"]["args"])}
            out.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": m["id"], "type": "function", "function": function}]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["id"],
                        "content": m["content"]})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out
