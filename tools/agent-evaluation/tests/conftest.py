import socket
from collections.abc import Iterator

import pytest

from agent_evaluation.policy import configure_privacy

configure_privacy()


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []

    def reject(*args: object, **kwargs: object) -> None:
        attempts.append("network")
        raise AssertionError("unexpected_network")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
    yield
    assert not attempts
