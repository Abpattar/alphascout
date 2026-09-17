"""Offline tests for src.netfix IPv4 forcing."""
import socket

import src.netfix as netfix


def test_force_ipv4_is_idempotent():
    assert netfix.force_ipv4() is True
    shim1 = socket.getaddrinfo
    assert netfix.force_ipv4() is True
    assert socket.getaddrinfo is shim1  # not wrapped twice


def test_getaddrinfo_forces_af_INET():
    # localhost resolves via /etc/hosts; the shim must request AF_INET only
    infos = socket.getaddrinfo("localhost", 443)
    assert infos, "expected at least one addrinfo"
    for family, _type, _proto, _canonname, _sockaddr in infos:
        assert family == socket.AF_INET
