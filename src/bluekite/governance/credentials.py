"""One credential per tool call, with one scope. The shop API checks the scope."""

from dataclasses import dataclass

from bluekite.governance.identity import Identity
from bluekite.governance.registry import ToolSpec


@dataclass(frozen=True)
class Token:
    scope: str  # the only thing this token allows, for example "refunds:write"
    agent: str
    run_id: str


class ScopeError(Exception):
    """The token does not allow this action."""


def issue(identity: Identity, spec: ToolSpec) -> Token:
    return Token(spec.scope, identity.agent, identity.run_id)


def require(token: Token, scope: str) -> None:
    if token.scope != scope:
        raise ScopeError(f"token has scope {token.scope}, needs {scope}")
