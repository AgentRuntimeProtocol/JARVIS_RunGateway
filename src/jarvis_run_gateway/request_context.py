from __future__ import annotations

from contextvars import ContextVar, Token

_bearer_token_var: ContextVar[str | None] = ContextVar("jarvis_run_gateway_bearer_token", default=None)


def parse_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def get_bearer_token() -> str | None:
    return _bearer_token_var.get()


def set_bearer_token(token: str | None) -> Token[str | None]:
    return _bearer_token_var.set(token)


def reset_bearer_token(state: Token[str | None]) -> None:
    _bearer_token_var.reset(state)
