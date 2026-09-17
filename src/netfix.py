"""
Network reliability patch.

Some hosts (notably this project's deployment machines) have broken IPv6
routing: DNS returns AAAA records first and TCP connects to them blackhole,
which makes httpx / requests / aiohttp hang indefinitely despite timeouts.

This module forces IPv4 (AF_INET) resolution for the whole process via a
getaddrinfo shim. It is idempotent and applied by every network-touching
entry point so behaviour is identical no matter how the code is launched.

Disable with ALPHASCOUT_FORCE_IPV4=0 if your host is IPv6-only.
"""
import logging
import os
import socket as _socket

logger = logging.getLogger(__name__)

_applied = False


def force_ipv4() -> bool:
    """Force IPv4 DNS resolution process-wide. Idempotent; returns True if active."""
    global _applied
    if _applied:
        return True
    if os.environ.get("ALPHASCOUT_FORCE_IPV4", "1").strip().lower() in ("0", "false", "no", "off"):
        logger.info("IPv4 forcing disabled via ALPHASCOUT_FORCE_IPV4")
        return False

    orig_gai = _socket.getaddrinfo

    def _force_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return orig_gai(host, port, _socket.AF_INET, type, proto, flags)

    _socket.getaddrinfo = _force_ipv4
    _applied = True
    logger.debug("Forced IPv4 DNS resolution (broken-IPv6-routing workaround)")
    return True


# Apply on import — importing this module is the whole point.
force_ipv4()
