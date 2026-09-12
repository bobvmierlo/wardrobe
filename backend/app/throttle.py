"""Slowing down someone who is guessing passwords.

The login endpoint already writes a line to the audit trail for every failed
attempt, which answers "is someone knocking on the door?" beautifully and does
nothing whatsoever to stop them. A password of reasonable length is not going to
fall to an online attack, but the app lets people pick short ones and an
installation reachable from the internet should not hand out unlimited tries
regardless.

So after a handful of consecutive failures the answer becomes 429 for a while,
and the wait doubles with each further failure up to a ceiling. A correct
password clears the count immediately, which is what keeps this out of the way
of the person who simply mistyped twice.

Two keys are counted, and a block on either is enough:

* **the username** — this is the one that actually protects an account, and no
  amount of cleverness on the other side can dodge it;
* **the client address** — best effort. Behind a reverse proxy every request
  comes from 127.0.0.1, so ``X-Forwarded-For`` is read when present. That header
  is forgeable, and it does not matter: forging it spreads an attacker's own
  budget across made-up addresses while the username counter keeps ticking.
  It is there to stop one host working through a list of accounts.

In process, so it resets when the container restarts and is not shared between
workers. Both are fine here: the app runs a single worker by design (SQLite),
and a restart is not a tool an attacker has.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .logging_setup import get_logger

log = get_logger("throttle")


@dataclass
class _Attempts:
    failures: int = 0
    blocked_until: float = 0.0
    last_seen: float = field(default_factory=time.monotonic)


class LoginThrottle:
    """Consecutive-failure counters with a doubling delay."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        base_seconds: int = 30,
        max_seconds: int = 900,
    ) -> None:
        #: Failures allowed before the door starts closing.
        self.max_attempts = max(1, max_attempts)
        self.base_seconds = max(1, base_seconds)
        self.max_seconds = max(self.base_seconds, max_seconds)
        self._attempts: dict[str, _Attempts] = {}

    # -- housekeeping ----------------------------------------------------
    def _sweep(self, now: float) -> None:
        """Forget keys nobody has touched for an hour, so this cannot grow."""
        if len(self._attempts) < 512:
            return
        stale = [k for k, a in self._attempts.items() if now - a.last_seen > 3600]
        for key in stale:
            self._attempts.pop(key, None)

    def _delay_for(self, failures: int) -> int:
        over = failures - self.max_attempts
        if over < 0:
            return 0
        return min(self.base_seconds * (2**over), self.max_seconds)

    # -- the two questions the login route asks ---------------------------
    def retry_after(self, *keys: str) -> int:
        """Seconds the caller must wait, or 0 when they may try now."""
        now = time.monotonic()
        self._sweep(now)
        longest = 0
        for key in keys:
            entry = self._attempts.get(key)
            if entry is None:
                continue
            remaining = entry.blocked_until - now
            if remaining > 0:
                longest = max(longest, int(remaining) + 1)
        return longest

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        for key in keys:
            entry = self._attempts.setdefault(key, _Attempts())
            entry.failures += 1
            entry.last_seen = now
            delay = self._delay_for(entry.failures)
            if delay:
                entry.blocked_until = now + delay
                log.warning(
                    "Te veel mislukte inlogpogingen (%d) voor %s — %d seconden op slot",
                    entry.failures,
                    key,
                    delay,
                )

    def record_success(self, *keys: str) -> None:
        """A correct password forgives everything that came before it."""
        for key in keys:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        """Forget every counter. For the tests."""
        self._attempts.clear()


#: The one the login route uses. Configured from settings at import time; the
#: tests build their own instances instead of reaching in here.
def _build() -> LoginThrottle:
    from .config import settings

    return LoginThrottle(
        max_attempts=settings.login_max_attempts,
        base_seconds=settings.login_lockout_seconds,
    )


login_throttle = _build()


def client_key(client_host: str | None, forwarded_for: str | None) -> str:
    """The address half of the key, preferring what a proxy forwarded."""
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return f"ip:{first}"
    return f"ip:{client_host or 'onbekend'}"
