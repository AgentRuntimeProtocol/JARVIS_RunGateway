import sys
from types import SimpleNamespace

import pytest

import jarvis_run_gateway.__main__ as main_mod


def test_load_uvicorn_missing(monkeypatch) -> None:
    def _raise(name):  # type: ignore[no-untyped-def]
        raise ImportError("missing")

    monkeypatch.setattr(main_mod.importlib, "import_module", _raise)
    with pytest.raises(SystemExit) as exc:
        main_mod._load_uvicorn()
    assert "uvicorn is not installed" in str(exc.value)


def test_main_reload_path(monkeypatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _run(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((args, kwargs))

    uvicorn = SimpleNamespace(run=_run)
    monkeypatch.setattr(main_mod, "_load_uvicorn", lambda: uvicorn)
    monkeypatch.setattr(sys, "argv", ["prog", "--reload", "--host", "0.0.0.0", "--port", "9999"])

    main_mod.main()

    assert calls
    args, kwargs = calls[0]
    assert args[0] == "jarvis_run_gateway.app:app"
    assert kwargs["reload"] is True
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9999


def test_main_non_reload_path(monkeypatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _run(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((args, kwargs))

    uvicorn = SimpleNamespace(run=_run)
    monkeypatch.setattr(main_mod, "_load_uvicorn", lambda: uvicorn)
    monkeypatch.setattr(sys, "argv", ["prog", "--host", "127.0.0.1", "--port", "7777"])

    monkeypatch.setenv("JARVIS_RUN_COORDINATOR_URL", "http://coordinator.test")
    monkeypatch.setenv("ARP_AUTH_PROFILE", "dev-insecure")
    monkeypatch.setenv("ARP_AUTH_CLIENT_ID", "arp-run-gateway")
    monkeypatch.setenv("ARP_AUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ARP_AUTH_TOKEN_ENDPOINT", "http://sts.test/token")

    main_mod.main()

    assert calls
    args, kwargs = calls[0]
    assert kwargs["reload"] is False
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 7777
