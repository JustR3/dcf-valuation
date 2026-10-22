"""Offline guard: any test not marked `integration` that opens an IP socket fails."""

from __future__ import annotations

import socket

import pytest

_IP_FAMILIES = (socket.AF_INET, socket.AF_INET6)
_orig_init = socket.socket.__init__


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: test may use the network (excluded from offline runs)")


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        return

    def guarded_init(self, family=-1, *args, **kwargs):
        fam = socket.AF_INET if family == -1 else family
        if fam in _IP_FAMILIES:
            pytest.fail(
                "network access in a test not marked @pytest.mark.integration "
                f"(socket family {fam!r})",
                pytrace=False,
            )
        _orig_init(self, family, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "__init__", guarded_init)
