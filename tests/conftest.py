import socket

import pytest


@pytest.fixture(autouse=True)
def _offline_and_keyless(monkeypatch, request):
    """Ordinary tests: no network, no real API key in the environment."""
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _blocked(*args, **kwargs):
        raise RuntimeError("Network access is blocked in ordinary tests.")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
