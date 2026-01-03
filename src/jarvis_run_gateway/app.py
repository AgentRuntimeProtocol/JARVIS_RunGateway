from __future__ import annotations

import logging

from fastapi import Request

from .gateway import RunGateway
from .request_context import parse_bearer_token, reset_bearer_token, set_bearer_token
from .utils import auth_settings_from_env_or_dev_secure

logger = logging.getLogger(__name__)


def create_app():
    auth_settings = auth_settings_from_env_or_dev_secure()
    logger.info(
        "Run Gateway auth settings (mode=%s, issuer=%s)",
        getattr(auth_settings, "mode", None),
        getattr(auth_settings, "issuer", None),
    )
    app = RunGateway().create_app(
        title="JARVIS Run Gateway",
        auth_settings=auth_settings,
    )

    @app.middleware("http")
    async def _capture_bearer_token(request: Request, call_next):  # type: ignore[no-untyped-def]
        token_state = set_bearer_token(parse_bearer_token(request.headers.get("Authorization")))
        try:
            return await call_next(request)
        finally:
            reset_bearer_token(token_state)

    return app


app = create_app()
